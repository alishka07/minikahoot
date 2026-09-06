"""WebSocket-протокол комнаты.

Сервер -> клиент:
  state_sync      полный снимок состояния (при подключении, после join и по запросу sync)
  lobby_update    кто-то зашёл/вышел/переподключился + актуальный список участников
  countdown       вопрос назначен: starts_at/ends_at, можно прогревать картинку
  game_started    вопрос открыт (у всех в один и тот же момент starts_at)
  tick            раз в секунду: остаток времени, кто ответил и за сколько
  stats_update    кто-то ответил (хосту - ещё и распределение по вариантам)
  question_ended  время вышло: правильные варианты, полная статистика, рейтинг
  game_finished   игра завершена, итоговый рейтинг
  answer_result   личный ответ игроку: принят/нет, верно ли, текущий счёт
  joined          личное: participant_id и токен для переподключения
  pong            личное: синхронизация часов (server_time/client_time)
  error           личное: текст ошибки

Клиент -> сервер:
  join_lobby {name, token?} | sync | ping {t}
  submit_answer {question_id, option_id|option_ids}
  start_game | show_question {question_id} | next_question | end_question | finish_game | reset_game  (только хост)
"""
import logging,time
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from urllib.parse import parse_qs
from . import engine,services
from .models import GameSession as S

log=logging.getLogger('game')
LIVE=(S.COUNTDOWN,S.QUESTION)
FLOOD_WINDOW,FLOOD_LIMIT=5.0,40

class QuizConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.code=self.scope['url_route']['kwargs']['room_code']
        self.group=engine.group_of(self.code)
        self.participant_id=None
        self.name=''
        self._hits=[]
        query={key:values[0] for key,values in parse_qs(self.scope['query_string'].decode()).items()}
        self.role=query.get('role','player')
        self.token=query.get('token','')
        self.player_token=query.get('player','')
        if not await database_sync_to_async(services.room_exists)(self.code):
            await self.close(code=4404); return
        self.is_host=await self.check_host()
        if self.role=='host' and not self.is_host:
            await self.close(code=4403); return
        await self.channel_layer.group_add(self.group,self.channel_name)
        await self.accept()
        await self.push_state()

    async def check_host(self):
        if self.role!='host': return False
        if not settings.QUIZ['REQUIRE_HOST_TOKEN']:
            if not self.token: log.warning('room %s: хост без токена (REQUIRE_HOST_TOKEN выключен)',self.code)
            return True
        return await database_sync_to_async(services.is_host_token)(self.code,self.token)

    async def disconnect(self,code):
        if getattr(self,'participant_id',None):
            player,event=await database_sync_to_async(services.detach)(self.participant_id)
            if player is not None and event is not None:
                await self.broadcast_presence('left',player,event)
        if getattr(self,'group',None):
            await self.channel_layer.group_discard(self.group,self.channel_name)

    # ------------------------------------------------------------ входящие сообщения
    async def receive_json(self,data,**kwargs):
        if self.flooding(): return
        handlers={'join_lobby':self.join_lobby,'sync':self.sync,'ping':self.ping,
                  'submit_answer':self.submit_answer,'start_game':self.start_game,
                  'show_question':self.show_question,'next_question':self.next_question,
                  'end_question':self.end_question,'finish_game':self.finish_game,
                  'reset_game':self.reset_game}
        handler=handlers.get(data.get('type') if isinstance(data,dict) else None)
        if handler is None: return
        try: await handler(data)
        except Exception:
            log.exception('room %s: ошибка обработки %s',self.code,data.get('type'))
            await self.send_json({'type':'error','message':'Внутренняя ошибка сервера'})

    def flooding(self):
        moment=time.monotonic()
        self._hits=[hit for hit in self._hits if moment-hit<FLOOD_WINDOW]
        self._hits.append(moment)
        return len(self._hits)>FLOOD_LIMIT

    async def require_host(self):
        if self.is_host: return True
        await self.send_json({'type':'error','message':'Только ведущий может управлять игрой'})
        return False

    async def join_lobby(self,data):
        name=str(data.get('name','')).strip()[:32]
        if not name:
            await self.send_json({'type':'error','message':'Имя обязательно'}); return
        try:
            player,event=await database_sync_to_async(services.register)(
                self.code,name,data.get('token') or self.player_token)
        except Exception:
            await self.send_json({'type':'error','message':'Не удалось войти в комнату'}); raise
        self.participant_id,self.name=player['id'],player['name']
        await self.send_json({'type':'joined','participant_id':player['id'],'token':player['token'],
                              'name':player['name'],'score':player['score'],'server_time':services.now_ms()})
        await self.push_state()
        await self.broadcast_presence(event['kind'],{'id':player['id'],'name':player['name'],'is_online':True},event)

    async def sync(self,data): await self.push_state()

    async def ping(self,data):
        if self.participant_id: await database_sync_to_async(services.touch)(self.participant_id)
        await self.send_json({'type':'pong','server_time':services.now_ms(),'client_time':data.get('t')})

    async def start_game(self,data):
        if not await self.require_host(): return
        session,error=await database_sync_to_async(services.start_game)(self.code)
        if error: await self.send_json({'type':'error','message':error}); return
        await self.broadcast_snapshot('game.countdown')
        engine.ensure(self.code)

    async def show_question(self,data): await self.jump(data.get('question_id'))
    async def next_question(self,data): await self.jump(None)

    async def jump(self,question_id):
        if not await self.require_host(): return
        session,finished=await engine.advance_now(self.code,question_id)
        if session is None: await self.send_json({'type':'error','message':'Вопрос не найден'})

    async def end_question(self,data):
        if not await self.require_host(): return
        await engine.close_now(self.code,forced=True)

    async def finish_game(self,data):
        if not await self.require_host(): return
        await database_sync_to_async(services.finish_game)(self.code)
        await engine.stop(self.code)
        await self.broadcast_snapshot('game.finished')

    async def reset_game(self,data):
        if not await self.require_host(): return
        await engine.stop(self.code)
        await database_sync_to_async(services.reset_game)(self.code)
        await self.broadcast_snapshot('game.reset',events=True)

    async def submit_answer(self,data):
        if not self.participant_id:
            await self.send_json({'type':'answer_result','accepted':False,'reason':'not_registered'}); return
        option_ids=data.get('option_ids') or ([data.get('option_id')] if data.get('option_id') is not None else [])
        result,stats,event=await database_sync_to_async(services.submit)(
            self.code,self.participant_id,data.get('question_id'),option_ids)
        await self.send_json({'type':'answer_result',**result})
        if not result['accepted']: return
        participants=await database_sync_to_async(services.participants_now)(self.code)
        await self.channel_layer.group_send(self.group,{'type':'game.answer','stats':stats,'event':event,
                                                        'participants':participants,
                                                        'server_time':services.now_ms()})
        engine.nudge(self.code)  # ответил последний - цикл закроет вопрос сразу, не дожидаясь тика

    # ------------------------------------------------------------ рассылка
    async def push_state(self):
        payload=await database_sync_to_async(services.snapshot)(self.code,self.participant_id,self.is_host)
        if payload is None: return
        await self.send_json(payload)
        if payload['status'] in LIVE or (payload['status']==S.REVEAL and payload['auto_advance']):
            engine.ensure(self.code)  # поднять цикл после рестарта процесса

    async def broadcast_snapshot(self,kind,events=False):
        payload=await database_sync_to_async(services.snapshot)(self.code,host=True,events=events)
        await self.channel_layer.group_send(self.group,{'type':kind,'payload':payload})

    async def broadcast_presence(self,kind,player,event):
        participants=await database_sync_to_async(services.participants_now)(self.code)
        await self.channel_layer.group_send(self.group,{'type':'game.presence','event':kind,'participant':player,
                                                        'participants':participants,'feed':event,
                                                        'server_time':services.now_ms()})

    def visible(self,payload):
        """Снимок под роль: игрок не видит правильные варианты и распределение, пока вопрос идёт."""
        data=dict(payload)
        if self.is_host or data.get('status') in (S.REVEAL,S.FINISHED): return data
        question=data.get('question')
        if question:
            question=dict(question); question.pop('correct_options',None); data['question']=question
        if data.get('stats'): data['stats']=services.public_stats(data['stats'])
        me=data.get('me')
        if me and me.get('answer') and data.get('status')==S.QUESTION:
            me=dict(me); me['answer']=dict(me['answer'],is_correct=None); data['me']=me
        return data

    # ------------------------------------------------------------ обработчики групповых событий
    async def game_presence(self,event):
        await self.send_json({'type':'lobby_update','event':event['event'],'participant':event['participant'],
                              'participants':event['participants'],'feed':event['feed'],
                              'server_time':event['server_time']})

    async def game_countdown(self,event):
        data=self.visible(event['payload'])
        await self.send_json({'type':'countdown','question':data['question'],'starts_at':data['starts_at'],
                              'ends_at':data['ends_at'],'index':data['index'],'total':data['total'],
                              'status':data['status'],'participants':data['participants'],
                              'server_time':services.now_ms()})

    async def game_question(self,event):
        data=self.visible(event['payload'])
        await self.send_json({'type':'game_started','question':data['question'],'starts_at':data['starts_at'],
                              'ends_at':data['ends_at'],'index':data['index'],'total':data['total'],
                              'status':data['status'],'participants':data['participants'],
                              'stats':data['stats'],'server_time':services.now_ms()})

    async def game_tick(self,event):
        frame=event['frame']
        stats=frame['stats'] if self.is_host else services.public_stats(frame['stats'])
        await self.send_json({'type':'tick','status':frame['status'],'question_id':frame['question_id'],
                              'index':frame['index'],'total':frame['total'],'ends_at':frame['ends_at'],
                              'remaining_ms':frame['remaining_ms'],'participants':frame['participants'],
                              'answered_count':stats['answered_count'],'online_count':stats['online_count'],
                              **({'answer_counts':stats['answer_counts']} if self.is_host else {}),
                              'stats':stats,'server_time':frame['server_time']})

    async def game_answer(self,event):
        stats=event['stats'] if self.is_host else services.public_stats(event['stats'])
        await self.send_json({'type':'stats_update','participants':event['participants'],
                              'answered_count':stats['answered_count'],
                              'answer_counts':stats.get('answer_counts',{}),
                              'stats':stats,'feed':event['event'],'server_time':event['server_time']})

    async def game_closed(self,event):
        data=event['payload']  # на этапе результатов правильные варианты показываем всем
        await self.send_json({'type':'question_ended','question':data['question'],'stats':event['stats'],
                              'answered_count':event['stats']['answered_count'],
                              'answer_counts':event['stats']['answer_counts'],
                              'participants':data['participants'],'leaderboard':data['leaderboard'],
                              'index':data['index'],'total':data['total'],'status':data['status'],
                              'reveal_ends_at':data['reveal_ends_at'],'server_time':services.now_ms()})

    async def game_finished(self,event):
        data=event['payload']
        await self.send_json({'type':'game_finished','participants':data['participants'],
                              'leaderboard':data['leaderboard'],'status':data['status'],
                              'server_time':services.now_ms()})

    async def game_reset(self,event):
        data=self.visible(event['payload'])
        await self.send_json({**data,'type':'state_sync'})
