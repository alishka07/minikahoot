"""Тесты на два ключевых требования: синхронный старт и живой таймер со статистикой.

Запуск: python manage.py test game --settings=quiz.settings_test
"""
from datetime import timedelta
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TestCase,TransactionTestCase
from django.utils import timezone
from . import engine,services
from .models import Answer,GameEvent,GameSession,Participant,Question,Room
from .routing import websocket_urlpatterns

APP=URLRouter(websocket_urlpatterns)

def make_room(count=2,duration=2):
    room=Room.objects.create(title='Тест')
    for index in range(count):
        Question.objects.create(room=room,order=index+1,text=f'Вопрос {index+1}',
                                options=[{'id':'a','text':'Да'},{'id':'b','text':'Нет'}],
                                correct_option='a',correct_options=['a'],duration_seconds=duration)
    return room

# ------------------------------------------------------------------ логика без сокетов
class ServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room=make_room()
        self.code=self.room.room_code

    def shift_window(self,milliseconds):
        """Сдвигает окно вопроса в прошлое, чтобы не ждать реальные секунды."""
        session=self.room.session
        session.starts_at=timezone.now()-timedelta(milliseconds=milliseconds)
        session.ends_at=session.starts_at+timedelta(seconds=2)
        session.save(update_fields=['starts_at','ends_at'])
        return session

    def test_start_sets_shared_future_deadline(self):
        services.register(self.code,'Алия')
        session,error=services.start_game(self.code)
        self.assertIsNone(error)
        self.assertEqual(session.status,GameSession.COUNTDOWN)
        self.assertGreater(session.starts_at,timezone.now())          # старт в будущем: все успевают получить событие
        self.assertEqual(session.ends_at-session.starts_at,timedelta(seconds=2))
        self.assertEqual(session.total,2)

    def test_start_requires_questions(self):
        empty=Room.objects.create()
        session,error=services.start_game(empty.room_code)
        self.assertIsNone(session)
        self.assertTrue(error)

    def test_answer_before_deadline_scores_by_speed(self):
        fast,_=services.register(self.code,'Быстрый')
        slow,_=services.register(self.code,'Медленный')
        services.start_game(self.code)
        self.shift_window(milliseconds=200)
        services.open_question(self.code)
        first,stats,event=services.submit(self.code,fast['id'],None,['a'])
        self.assertTrue(first['accepted'])
        self.assertTrue(first['correct'])
        self.assertEqual(stats['answered_count'],1)
        self.assertEqual(event['kind'],GameEvent.ANSWERED)
        self.assertIn('response_ms',event)
        self.shift_window(milliseconds=1800)
        second,_,_=services.submit(self.code,slow['id'],None,['a'])
        self.assertTrue(second['accepted'])
        self.assertGreater(first['points'],second['points'])          # кто быстрее, тот больше очков
        self.assertGreaterEqual(second['points'],1000*services.cfg('MIN_RATIO')-1)

    def test_wrong_answer_scores_zero(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        result,_,_=services.submit(self.code,player['id'],None,['b'])
        self.assertTrue(result['accepted'])
        self.assertFalse(result['correct'])
        self.assertEqual(result['score'],0)

    def test_late_answer_is_rejected(self):
        player,_=services.register(self.code,'Опоздавший')
        services.start_game(self.code)
        services.open_question(self.code)
        session=self.room.session
        session.ends_at=timezone.now()-timedelta(seconds=5)
        session.save(update_fields=['ends_at'])
        result,_,_=services.submit(self.code,player['id'],None,['a'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'],'timeout')

    def test_double_answer_is_rejected(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        services.submit(self.code,player['id'],None,['a'])
        again,_,_=services.submit(self.code,player['id'],None,['b'])
        self.assertFalse(again['accepted'])
        self.assertEqual(again['reason'],'duplicate')
        self.assertEqual(Answer.objects.count(),1)

    def test_answer_for_other_question_is_rejected(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        other=self.room.questions.last()
        result,_,_=services.submit(self.code,player['id'],other.id,['a'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'],'stale_question')

    def test_flow_advance_and_finish(self):
        services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        session,stats=services.close_question(self.code)
        self.assertEqual(session.status,GameSession.REVEAL)
        self.assertEqual(stats['answered_count'],0)
        session,finished=services.advance(self.code)
        self.assertFalse(finished)
        self.assertEqual(session.current_index,1)
        self.assertEqual(session.status,GameSession.COUNTDOWN)
        session,finished=services.advance(self.code)
        self.assertTrue(finished)
        self.assertEqual(session.status,GameSession.FINISHED)
        self.assertIsNone(session.current_question_id)

    def test_snapshot_hides_answers_from_players_during_question(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        for_player=services.snapshot(self.code,player['id'],host=False)
        for_host=services.snapshot(self.code,host=True)
        self.assertNotIn('correct_options',for_player['question'])
        self.assertIn('correct_options',for_host['question'])
        self.assertNotIn('answer_counts',for_player['stats'])
        self.assertIn('answer_counts',for_host['stats'])

    def test_reveal_shows_correct_options_to_players(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        services.close_question(self.code)
        payload=services.snapshot(self.code,player['id'],host=False)
        self.assertEqual(payload['question']['correct_options'],['a'])

    def test_presence_counts_connections(self):
        player,event=services.register(self.code,'Игрок')
        self.assertEqual(event['kind'],GameEvent.JOINED)
        services.register(self.code,'Игрок')                          # второе устройство/вкладка
        self.assertEqual(Participant.objects.get(id=player['id']).connections,2)
        services.detach(player['id'])
        self.assertTrue(Participant.objects.get(id=player['id']).is_online)
        row,left=services.detach(player['id'])
        self.assertFalse(row['is_online'])
        self.assertEqual(left['kind'],GameEvent.LEFT)

    def test_reset_clears_scores_but_keeps_players(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        services.submit(self.code,player['id'],None,['a'])
        self.assertGreater(Participant.objects.get(id=player['id']).score,0)
        services.reset_game(self.code)
        row=Participant.objects.get(id=player['id'])
        self.assertEqual(row.score,0)
        self.assertEqual(row.session,self.room.session)

    def test_results_report_contains_response_times(self):
        player,_=services.register(self.code,'Игрок')
        services.start_game(self.code)
        services.open_question(self.code)
        services.submit(self.code,player['id'],None,['a'])
        report=services.results(self.code)
        first=report['questions'][0]
        self.assertEqual(first['answered_count'],1)
        self.assertEqual(first['answer_counts'],{'a':1})
        self.assertEqual(first['answers'][0]['name'],'Игрок')
        self.assertIsNotNone(first['avg_response_ms'])
        self.assertEqual(report['leaderboard'][0]['name'],'Игрок')

# ------------------------------------------------------------------ сокеты и движок
class LiveGameTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.room=make_room()
        self.code=self.room.room_code

    async def ws(self,role='player',token=''):
        client=WebsocketCommunicator(APP,f'/ws/quiz/{self.code}/?role={role}&token={token}')
        connected,_=await client.connect()
        self.assertTrue(connected)
        await self.expect(client,'state_sync')
        return client

    async def join(self,name):
        client=await self.ws()
        await client.send_json_to({'type':'join_lobby','name':name})
        await self.expect(client,'joined')
        return client

    async def expect(self,client,kind,timeout=6):
        """Ждём сообщение нужного типа, пропуская остальные."""
        while True:
            message=await client.receive_json_from(timeout=timeout)
            if message['type']==kind: return message

    async def shutdown(self,*clients):
        await engine.stop(self.code)
        for client in clients: await client.disconnect()

    async def test_start_opens_question_at_one_moment_for_everyone(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        second=await self.join('Бахыт')
        await host.send_json_to({'type':'start_game'})
        countdown_a=await self.expect(first,'countdown')
        countdown_b=await self.expect(second,'countdown')
        self.assertEqual(countdown_a['starts_at'],countdown_b['starts_at'])   # один и тот же момент T0
        self.assertEqual(countdown_a['ends_at'],countdown_b['ends_at'])
        self.assertGreater(countdown_a['starts_at'],countdown_a['server_time'])
        opened_a=await self.expect(first,'game_started')
        opened_b=await self.expect(second,'game_started')
        opened_host=await self.expect(host,'game_started')
        self.assertEqual(opened_a['ends_at'],opened_b['ends_at'])
        self.assertEqual(opened_a['ends_at'],opened_host['ends_at'])
        self.assertEqual(opened_a['starts_at'],countdown_a['starts_at'])
        self.assertEqual(opened_a['ends_at']-opened_a['starts_at'],2000)      # окно ровно 10 (здесь 2) секунд
        self.assertNotIn('correct_options',opened_a['question'])
        self.assertIn('correct_options',opened_host['question'])
        await self.shutdown(host,first,second)

    async def test_late_joiner_lands_in_the_running_question(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await host.send_json_to({'type':'start_game'})
        opened=await self.expect(first,'game_started')
        late=WebsocketCommunicator(APP,f'/ws/quiz/{self.code}/?role=player')
        connected,_=await late.connect()
        self.assertTrue(connected)
        state=await self.expect(late,'state_sync')
        self.assertEqual(state['status'],'question')
        self.assertEqual(state['ends_at'],opened['ends_at'])                  # тот же дедлайн, что у всех
        self.assertEqual(state['question']['id'],opened['question']['id'])
        self.assertGreater(state['ends_at'],state['server_time'])
        await self.shutdown(host,first,late)

    async def test_presence_is_broadcast_to_everyone(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        second=await self.join('Бахыт')
        joined=await self.expect(host,'lobby_update')
        while joined['participant']['name']!='Бахыт':
            joined=await self.expect(host,'lobby_update')
        self.assertEqual(joined['event'],'joined')
        self.assertEqual(joined['feed']['kind'],'joined')
        self.assertEqual({row['name'] for row in joined['participants']},{'Алия','Бахыт'})
        await second.disconnect()
        left=await self.expect(first,'lobby_update')
        while left['event']!='left':
            left=await self.expect(first,'lobby_update')
        self.assertEqual(left['participant']['name'],'Бахыт')
        self.assertFalse(left['participant']['is_online'])
        await self.shutdown(host,first)

    async def test_answer_is_broadcast_live_with_response_time(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        second=await self.join('Бахыт')
        await host.send_json_to({'type':'start_game'})
        opened=await self.expect(first,'game_started')
        await first.send_json_to({'type':'submit_answer','question_id':opened['question']['id'],'option_ids':['a']})
        result=await self.expect(first,'answer_result')
        self.assertTrue(result['accepted'])
        self.assertTrue(result['correct'])
        self.assertGreater(result['score'],0)
        for_players=await self.expect(second,'stats_update')
        self.assertEqual(for_players['answered_count'],1)
        self.assertEqual(for_players['feed']['name'],'Алия')
        self.assertIn('response_ms',for_players['feed'])
        self.assertEqual(for_players['answer_counts'],{})                     # игроки не видят распределение
        for_host=await self.expect(host,'stats_update')
        self.assertEqual(for_host['answer_counts'],{'a':1})                   # ведущий видит
        self.assertEqual(for_host['stats']['answers'][0]['name'],'Алия')
        answered=[row for row in for_host['participants'] if row['name']=='Алия'][0]
        self.assertEqual(answered['stage'],'answered')
        self.assertTrue(answered['answered'])
        await self.shutdown(host,first,second)

    async def test_tick_broadcasts_remaining_time(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await host.send_json_to({'type':'start_game'})
        await self.expect(first,'game_started')
        tick=await self.expect(first,'tick')
        self.assertEqual(tick['status'],'question')
        self.assertLessEqual(tick['remaining_ms'],2000)
        self.assertGreaterEqual(tick['remaining_ms'],0)
        self.assertEqual(tick['total'],2)
        self.assertEqual(len(tick['participants']),1)
        await self.shutdown(host,first)

    async def test_question_closes_when_everyone_answered(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await host.send_json_to({'type':'start_game'})
        opened=await self.expect(first,'game_started')
        await first.send_json_to({'type':'submit_answer','question_id':opened['question']['id'],'option_ids':['a']})
        await self.expect(first,'answer_result')
        ended=await self.expect(first,'question_ended')
        self.assertEqual(ended['answer_counts'],{'a':1})
        self.assertEqual(ended['question']['correct_options'],['a'])          # на результатах ответ виден всем
        self.assertEqual(ended['stats']['correct_count'],1)
        self.assertEqual(ended['leaderboard'][0]['name'],'Алия')
        await self.shutdown(host,first)

    async def test_question_closes_on_timeout_without_answers(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await host.send_json_to({'type':'start_game'})
        await self.expect(first,'game_started')
        ended=await self.expect(first,'question_ended',timeout=8)             # сервер сам закрывает по таймеру
        self.assertEqual(ended['answered_count'],0)
        self.assertEqual(ended['status'],'reveal')
        await self.shutdown(host,first)

    async def test_player_cannot_control_the_game(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await first.send_json_to({'type':'start_game'})
        error=await self.expect(first,'error')
        self.assertIn('ведущий',error['message'])
        await self.shutdown(host,first)

    async def test_host_advances_to_next_question(self):
        host=await self.ws('host')
        first=await self.join('Алия')
        await host.send_json_to({'type':'start_game'})
        opened=await self.expect(first,'game_started')
        await host.send_json_to({'type':'end_question'})
        await self.expect(first,'question_ended')
        await host.send_json_to({'type':'next_question'})
        second=await self.expect(first,'game_started')
        self.assertNotEqual(second['question']['id'],opened['question']['id'])
        self.assertEqual(second['index'],2)
        await host.send_json_to({'type':'finish_game'})
        finished=await self.expect(first,'game_finished')
        self.assertEqual(finished['status'],'finished')
        await self.shutdown(host,first)

    async def test_unknown_room_is_rejected(self):
        client=WebsocketCommunicator(APP,'/ws/quiz/000000/?role=player')
        connected,code=await client.connect()
        self.assertFalse(connected)
        self.assertEqual(code,4404)

# ------------------------------------------------------------------ REST API
class ApiTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_room_creation_returns_host_token_once(self):
        created=self.client.post('/api/rooms/',data={},content_type='application/json')
        self.assertEqual(created.status_code,201)
        body=created.json()
        self.assertRegex(body['room_code'],r'^\d{6}$')
        self.assertIn('host_token',body)
        public=self.client.get(f'/api/rooms/{body["room_code"]}/').json()
        self.assertNotIn('host_token',public)                                  # чужой токен не утекает
        mine=self.client.get(f'/api/rooms/{body["room_code"]}/?token={body["host_token"]}').json()
        self.assertEqual(mine['host_token'],body['host_token'])

    def test_bulk_question_creation_numbers_the_order(self):
        room=Room.objects.create()
        payload=[{'text':'Первый','options':[{'id':'a','text':'1'},{'id':'b','text':'2'}],'correct_option':'a'},
                 {'text':'Второй','options':[{'id':'a','text':'1'},{'id':'b','text':'2'}],'correct_option':'b',
                  'duration_seconds':20}]
        response=self.client.post(f'/api/rooms/{room.room_code}/questions/',data=payload,
                                  content_type='application/json')
        self.assertEqual(response.status_code,201)
        rows=list(room.questions.all())
        self.assertEqual([row.order for row in rows],[1,2])
        self.assertEqual(rows[0].duration_seconds,services.cfg('QUESTION_SECONDS'))
        self.assertEqual(rows[1].duration_seconds,20)

    def test_question_validation_rejects_unknown_correct_option(self):
        room=Room.objects.create()
        response=self.client.post(f'/api/rooms/{room.room_code}/questions/',
                                  data={'text':'Плохой','options':[{'id':'a','text':'1'},{'id':'b','text':'2'}],
                                        'correct_option':'z'},content_type='application/json')
        self.assertEqual(response.status_code,400)

    def test_state_and_results_endpoints(self):
        room=make_room()
        player,_=services.register(room.room_code,'Игрок')
        services.start_game(room.room_code)
        services.open_question(room.room_code)
        services.submit(room.room_code,player['id'],None,['a'])
        state=self.client.get(f'/api/rooms/{room.room_code}/state/').json()
        self.assertEqual(state['status'],'question')
        self.assertEqual(state['total'],2)
        self.assertIsNotNone(state['ends_at'])
        self.assertNotIn('correct_options',state['question'])                  # без токена ответы скрыты
        as_host=self.client.get(f'/api/rooms/{room.room_code}/state/?token={room.host_token}').json()
        self.assertIn('correct_options',as_host['question'])
        results=self.client.get(f'/api/rooms/{room.room_code}/results/').json()
        self.assertEqual(results['leaderboard'][0]['name'],'Игрок')
        self.assertEqual(results['questions'][0]['answered_count'],1)
        events=self.client.get(f'/api/rooms/{room.room_code}/events/').json()
        kinds=[row['kind'] for row in events['events']]
        self.assertEqual(kinds[:2],['joined','game_started'])
        self.assertIn('answered',kinds)

    def test_events_feed_supports_incremental_polling(self):
        room=make_room()
        services.register(room.room_code,'Игрок')
        first=self.client.get(f'/api/rooms/{room.room_code}/events/').json()
        last_id=first['events'][-1]['id']
        services.start_game(room.room_code)
        again=self.client.get(f'/api/rooms/{room.room_code}/events/?after={last_id}').json()
        self.assertEqual([row['kind'] for row in again['events']],['game_started'])

    def test_unknown_room_returns_404(self):
        self.assertEqual(self.client.get('/api/rooms/000000/state/').status_code,404)
