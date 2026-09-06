"""Слой игровой логики: все переходы состояний и подсчёты живут здесь.

Источник правды по времени - сервер. В БД лежат абсолютные метки starts_at/ends_at,
поэтому любое устройство (в том числе подключившееся посреди вопроса) считает
остаток одинаково: ends_at - server_now.
"""
import logging
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError,transaction
from django.db.models import Avg,Count,F,Q
from django.utils import timezone
from .models import Answer,GameEvent,GameSession,Participant,Question,Room

log=logging.getLogger('game')
S=GameSession

def cfg(key): return settings.QUIZ[key]
def epoch(value): return None if value is None else round(value.timestamp()*1000)
def now(): return timezone.now()
def now_ms(): return epoch(timezone.now())

# ---------------------------------------------------------------- комнаты и сессии
def get_room(code): return Room.objects.filter(room_code=code,is_active=True).first()
def room_exists(code): return Room.objects.filter(room_code=code,is_active=True).exists()

def is_host_token(code,token):
    room=get_room(code)
    return bool(room and token and token==room.host_token)

def ensure_session(room,locked=False):
    """Текущая сессия комнаты; создаётся при первом обращении."""
    query=room.sessions.order_by('-id')
    if locked: query=query.select_for_update()
    session=query.first()
    if session is None:
        session=GameSession.objects.create(room=room,auto_advance=cfg('AUTO_ADVANCE'),
                                           question_order=list(room.questions.values_list('id',flat=True)))
    return session

def _locked_session(code):
    room=Room.objects.get(room_code=code,is_active=True)
    return room,ensure_session(room,locked=True)

def question_ids(room): return list(room.questions.values_list('id',flat=True))

# ---------------------------------------------------------------- сериализация
def question_payload(question,index,total,reveal=False):
    if question is None: return None
    data={'id':question.id,'text':question.text,'options':list(question.options),'image':question.image,
          'is_multiple':question.is_multiple,'duration':question.duration_seconds,
          'duration_ms':question.duration_seconds*1000,'max_points':question.max_points,
          'index':index+1,'total':total,'order':question.order}
    if reveal: data['correct_options']=question.expected
    return data

def participant_payload(participant,answered_ids=()):
    return {'id':participant.id,'name':participant.name,'score':participant.score,
            'is_online':participant.is_online,'connections':participant.connections,
            'stage':participant.stage,'current_index':participant.current_index,
            'current_question_id':participant.current_question_id,
            'answered':participant.id in answered_ids,
            'last_seen':epoch(participant.last_seen_at),'joined_at':epoch(participant.joined_at)}

def participants_payload(session):
    answered=set()
    if session.current_question_id:
        answered=set(Answer.objects.filter(session=session,question_id=session.current_question_id)
                     .values_list('participant_id',flat=True))
    rows=Participant.objects.filter(session=session).order_by('-score','name')
    return [participant_payload(row,answered) for row in rows]

def session_payload(session):
    return {'session_id':session.id,'status':session.status,
            'index':session.current_index+1 if session.total else 0,'total':session.total,
            'auto_advance':session.auto_advance,'starts_at':epoch(session.starts_at),
            'ends_at':epoch(session.ends_at),'reveal_ends_at':epoch(session.reveal_ends_at),
            'server_time':now_ms()}

# ---------------------------------------------------------------- живая статистика
def question_stats(session,question=None):
    """Полная статистика по вопросу: распределение, кто ответил и за сколько."""
    question=question or session.current_question
    online=Participant.objects.filter(session=session,is_online=True).count()
    players=Participant.objects.filter(session=session).count()
    if question is None:
        return {'question_id':None,'answered_count':0,'answer_counts':{},'correct_count':0,
                'online_count':online,'players_count':players,'avg_response_ms':None,
                'fastest_ms':None,'answers':[]}
    rows=list(Answer.objects.filter(session=session,question=question)
              .select_related('participant').order_by('response_ms','id'))
    counts={}
    for row in rows:
        for option_id in (row.option_ids or ([row.option_id] if row.option_id else [])):
            counts[str(option_id)]=counts.get(str(option_id),0)+1
    answers=[{'participant_id':row.participant_id,'name':row.participant.name,'response_ms':row.response_ms,
              'is_correct':row.is_correct,'points':row.points,'option_ids':row.option_ids} for row in rows]
    return {'question_id':question.id,'answered_count':len(rows),'answer_counts':counts,
            'correct_count':sum(1 for row in rows if row.is_correct),'online_count':online,
            'players_count':players,
            'avg_response_ms':round(sum(row.response_ms for row in rows)/len(rows)) if rows else None,
            'fastest_ms':rows[0].response_ms if rows else None,'answers':answers}

def public_stats(stats):
    """Версия для игроков, пока вопрос идёт: без распределения и правильности."""
    return {'question_id':stats['question_id'],'answered_count':stats['answered_count'],
            'online_count':stats['online_count'],'players_count':stats['players_count'],
            'avg_response_ms':stats['avg_response_ms'],'fastest_ms':stats['fastest_ms'],
            'answers':[{'participant_id':row['participant_id'],'name':row['name'],
                        'response_ms':row['response_ms']} for row in stats['answers']]}

def leaderboard(session):
    """Таблица для всех: помимо очков - сколько верных и как быстро отвечал участник."""
    stats={row['participant_id']:row for row in Answer.objects.filter(session=session)
           .values('participant_id')
           .annotate(correct=Count('id',filter=Q(is_correct=True)),answered=Count('id'),avg_ms=Avg('response_ms'))}
    rows=[]
    for row in Participant.objects.filter(session=session).order_by('-score','name'):
        stat=stats.get(row.id)
        rows.append({'id':row.id,'name':row.name,'score':row.score,'is_online':row.is_online,
                     'correct':stat['correct'] if stat else 0,
                     'answered':stat['answered'] if stat else 0,
                     'avg_response_ms':round(stat['avg_ms']) if stat and stat['avg_ms'] is not None else None})
    return rows

# ---------------------------------------------------------------- лента событий
def log_event(session,kind,participant=None,question=None,**payload):
    if participant is not None: payload.setdefault('name',participant.name)
    return GameEvent.objects.create(session=session,kind=kind,participant=participant,
                                    question=question,payload=payload).as_dict()

def recent_events(session,limit=None,after_id=None):
    query=session.events.all()
    if after_id: query=query.filter(id__gt=after_id)
    rows=list(query.order_by('-id')[:limit or cfg('EVENT_FEED_LIMIT')])
    return [row.as_dict() for row in reversed(rows)]

# ---------------------------------------------------------------- участники
def register(code,name,token=''):
    """Регистрация или переподключение игрока. Возвращает (participant, event)."""
    with transaction.atomic():
        room=Room.objects.get(room_code=code,is_active=True)
        session=ensure_session(room,locked=True)
        player=Participant.objects.select_for_update().filter(room=room,name=name).first()
        if player is None and token:
            player=Participant.objects.select_for_update().filter(room=room,token=token).first()
        if player is None:
            player=Participant.objects.create(room=room,session=session,name=name,is_online=True,
                                              connections=1,last_seen_at=now(),stage=Participant.WAITING)
            kind=GameEvent.JOINED
        else:
            rejoin=player.session_id==session.id and player.connections>0
            if player.session_id!=session.id:
                player.session=session; player.score=0; player.current_index=0
                player.stage=Participant.WAITING; player.current_question=None
            player.name=name; player.is_online=True; player.connections=player.connections+1
            player.last_seen_at=now()
            player.save()
            kind=GameEvent.REJOINED if (rejoin or session.is_live) else GameEvent.JOINED
        if session.is_live and session.current_question_id and player.stage==Participant.WAITING:
            player.stage=Participant.PLAYING
            player.current_index=session.current_index
            player.current_question_id=session.current_question_id
            player.save(update_fields=['stage','current_index','current_question'])
        event=log_event(session,kind,participant=player,connections=player.connections)
    return {'id':player.id,'name':player.name,'token':player.token,'score':player.score,
            'session_id':session.id},event

def detach(participant_id):
    """Разрыв соединения. Возвращает (participant_dict, event) - event только когда игрок ушёл совсем."""
    with transaction.atomic():
        player=Participant.objects.select_for_update().filter(id=participant_id).first()
        if player is None: return None,None
        player.connections=max(0,player.connections-1)
        player.is_online=player.connections>0
        player.last_seen_at=now()
        player.save(update_fields=['connections','is_online','last_seen_at'])
        session=player.session or player.room.sessions.order_by('-id').first()
        event=None
        if session is not None and not player.is_online:
            event=log_event(session,GameEvent.LEFT,participant=player,connections=0)
    return {'id':player.id,'name':player.name,'is_online':player.is_online},event

def touch(participant_id): Participant.objects.filter(id=participant_id).update(last_seen_at=now())

# ---------------------------------------------------------------- переходы состояний
def _schedule(session,question,lead_ms):
    """Ставит общий для всех момент открытия вопроса: T0 = now + lead."""
    moment=now()+timedelta(milliseconds=lead_ms)
    session.status=S.COUNTDOWN
    session.current_question=question
    session.starts_at=moment
    session.ends_at=moment+timedelta(seconds=question.duration_seconds)
    session.reveal_ends_at=None

def _new_session(room,previous):
    session=GameSession.objects.create(room=room,auto_advance=cfg('AUTO_ADVANCE'),
                                       question_order=question_ids(room))
    Participant.objects.filter(session=previous).update(session=session,score=0,current_index=0,
                                                        stage=Participant.WAITING,current_question=None)
    return session

def start_game(code):
    """Хост нажал Начать: всем участникам ставится один и тот же момент старта."""
    with transaction.atomic():
        room,session=_locked_session(code)
        ids=question_ids(room)
        if not ids: return None,'Добавьте хотя бы один вопрос'
        if session.status in (S.COUNTDOWN,S.QUESTION): return None,'Игра уже идёт'
        if session.status in (S.REVEAL,S.FINISHED): session=_new_session(room,session)
        session.question_order=ids
        session.current_index=0
        session.started_at=now()
        session.finished_at=None
        session.auto_advance=cfg('AUTO_ADVANCE')
        _schedule(session,room.questions.get(id=ids[0]),cfg('COUNTDOWN_MS'))
        session.save()
        Participant.objects.filter(session=session).update(stage=Participant.WAITING,current_index=0,
                                                           current_question=None)
        log_event(session,GameEvent.GAME_STARTED,total=len(ids),starts_at=epoch(session.starts_at))
    return session,None

def reset_game(code):
    """Новая сессия в той же комнате: очки обнуляются, игроки остаются."""
    with transaction.atomic():
        room,session=_locked_session(code)
        return _new_session(room,session)

def open_question(code):
    """Вызывается движком ровно в starts_at - вопрос открывается у всех одновременно."""
    with transaction.atomic():
        room,session=_locked_session(code)
        if session.status!=S.COUNTDOWN or session.current_question_id is None: return None
        question=session.current_question
        moment=now()
        if session.starts_at is None or moment>session.starts_at+timedelta(seconds=1):
            session.starts_at=moment
            session.ends_at=moment+timedelta(seconds=question.duration_seconds)
        session.status=S.QUESTION
        session.reveal_ends_at=None
        session.save(update_fields=['status','starts_at','ends_at','reveal_ends_at'])
        Participant.objects.filter(session=session).update(stage=Participant.PLAYING,
                                                           current_index=session.current_index,
                                                           current_question=question)
        log_event(session,GameEvent.QUESTION_OPENED,question=question,index=session.current_index+1,
                  total=session.total,ends_at=epoch(session.ends_at))
    return session

def close_question(code,forced=False):
    """Время вышло или хост закрыл вопрос досрочно."""
    with transaction.atomic():
        room,session=_locked_session(code)
        if session.status!=S.QUESTION: return None,None
        question=session.current_question
        moment=now()
        if forced and session.ends_at and moment<session.ends_at: session.ends_at=moment
        session.status=S.REVEAL
        session.reveal_ends_at=moment+timedelta(milliseconds=cfg('REVEAL_MS'))
        session.save(update_fields=['status','ends_at','reveal_ends_at'])
        answered=set(Answer.objects.filter(session=session,question=question)
                     .values_list('participant_id',flat=True))
        Participant.objects.filter(session=session).exclude(id__in=answered).update(stage=Participant.WAITING)
        stats=question_stats(session,question)
        log_event(session,GameEvent.QUESTION_CLOSED,question=question,answered=stats['answered_count'],
                  correct=stats['correct_count'],avg_response_ms=stats['avg_response_ms'])
    return session,stats

def _finish(session):
    session.status=S.FINISHED
    session.finished_at=now()
    session.current_question=None
    session.starts_at=session.ends_at=session.reveal_ends_at=None
    session.save()
    Participant.objects.filter(session=session).update(stage=Participant.FINISHED,current_question=None)
    log_event(session,GameEvent.GAME_FINISHED,leaderboard=leaderboard(session)[:10])
    return session

def advance(code,question_id=None):
    """Следующий вопрос (или конкретный по id). Возвращает (session, finished)."""
    with transaction.atomic():
        room,session=_locked_session(code)
        ids=question_ids(room)
        if not ids: return None,False
        session.question_order=ids
        if question_id is not None:
            try: index=ids.index(int(question_id))
            except (ValueError,TypeError): return None,False
        else:
            index=session.current_index+1 if session.status!=S.LOBBY else 0
        if index>=len(ids): return _finish(session),True
        session.current_index=index
        if session.started_at is None: session.started_at=now()
        _schedule(session,room.questions.get(id=ids[index]),cfg('NEXT_LEAD_MS'))
        session.save()
        Participant.objects.filter(session=session).update(stage=Participant.WAITING)
    return session,False

def finish_game(code):
    with transaction.atomic():
        room,session=_locked_session(code)
        return session if session.status==S.FINISHED else _finish(session)

# ---------------------------------------------------------------- ответы
def submit(code,participant_id,question_id,option_ids):
    """Приём ответа. Дедлайн и время реакции считает сервер, а не клиент."""
    with transaction.atomic():
        room,session=_locked_session(code)
        question=session.current_question
        if session.status!=S.QUESTION or question is None:
            return {'accepted':False,'reason':'closed'},None,None
        if question_id not in (None,'') and str(question_id)!=str(question.id):
            return {'accepted':False,'reason':'stale_question'},None,None
        moment=now()
        if session.ends_at and moment>session.ends_at+timedelta(milliseconds=cfg('GRACE_MS')):
            return {'accepted':False,'reason':'timeout'},None,None
        player=Participant.objects.select_for_update().filter(id=participant_id,session=session).first()
        if player is None: return {'accepted':False,'reason':'not_registered'},None,None
        duration_ms=question.duration_seconds*1000
        elapsed=(moment-session.starts_at).total_seconds()*1000 if session.starts_at else 0
        elapsed=int(min(max(elapsed,0),duration_ms))
        chosen=[str(value) for value in dict.fromkeys(option_ids or []) if str(value)]
        correct=bool(chosen) and set(chosen)==set(question.expected)
        ratio=1-(elapsed/duration_ms)*(1-cfg('MIN_RATIO')) if duration_ms else 1
        points=int(round(question.max_points*ratio)) if correct else 0
        try:
            with transaction.atomic():
                Answer.objects.create(session=session,participant=player,question=question,
                                      option_id=chosen[0] if len(chosen)==1 else '',option_ids=chosen,
                                      is_correct=correct,points=points,response_ms=elapsed)
        except IntegrityError:
            return {'accepted':False,'reason':'duplicate'},None,None
        Participant.objects.filter(id=player.id).update(score=F('score')+points,stage=Participant.ANSWERED,
                                                        current_index=session.current_index,
                                                        current_question=question,last_seen_at=moment)
        player.score+=points  # строка под select_for_update: значение известно без ещё одного рейса к БД
        event=log_event(session,GameEvent.ANSWERED,participant=player,question=question,
                        response_ms=elapsed,index=session.current_index+1)
        stats=question_stats(session,question)
    return {'accepted':True,'correct':correct,'score':player.score,'points':points,
            'response_ms':elapsed},stats,event

def everyone_answered(session):
    if session.current_question_id is None: return False
    online=Participant.objects.filter(session=session,is_online=True).count()
    if not online: return False
    answered=Answer.objects.filter(session=session,question_id=session.current_question_id,
                                   participant__is_online=True).count()
    return answered>=online

# ---------------------------------------------------------------- снимки состояния
def participants_now(code):
    room=get_room(code)
    return [] if room is None else participants_payload(ensure_session(room))

def snapshot(code,participant_id=None,host=False,events=True):
    """Полное состояние комнаты - для новых подключений и ресинхронизации."""
    room=get_room(code)
    if room is None: return None
    session=ensure_session(room)
    reveal=host or session.status in (S.REVEAL,S.FINISHED)
    stats=question_stats(session)
    payload={'type':'state_sync','room_code':room.room_code,'title':room.title,**session_payload(session),
             'question':question_payload(session.current_question,session.current_index,session.total,reveal=reveal),
             'participants':participants_payload(session),'leaderboard':leaderboard(session),
             'stats':stats if reveal else public_stats(stats),
             'events':recent_events(session,limit=40) if events else []}
    if participant_id:
        player=Participant.objects.filter(id=participant_id).first()
        if player is not None:
            answer=(Answer.objects.filter(session=session,participant=player,
                                          question_id=session.current_question_id).first()
                    if session.current_question_id else None)
            payload['me']={'participant_id':player.id,'name':player.name,'score':player.score,
                           'stage':player.stage,'token':player.token,'answered':answer is not None,
                           'answer':{'option_ids':answer.option_ids,'response_ms':answer.response_ms,
                                     'points':answer.points if reveal else None,
                                     'is_correct':answer.is_correct} if answer else None}
    return payload

def engine_state(code):
    """Компактное состояние для игрового цикла."""
    room=get_room(code)
    if room is None: return None
    session=ensure_session(room)
    return {'status':session.status,
            'starts_at':session.starts_at.timestamp() if session.starts_at else None,
            'ends_at':session.ends_at.timestamp() if session.ends_at else None,
            'reveal_ends_at':session.reveal_ends_at.timestamp() if session.reveal_ends_at else None,
            'auto_advance':session.auto_advance,'index':session.current_index,'total':session.total,
            'question_id':session.current_question_id,'all_answered':everyone_answered(session)}

def live_frame(code):
    """Кадр лайв-трансляции: кто где, сколько ответили, сколько осталось."""
    room=get_room(code)
    if room is None: return None
    session=ensure_session(room)
    remaining=None
    if session.ends_at and session.status==S.QUESTION:
        remaining=max(0,round((session.ends_at-now()).total_seconds()*1000))
    return {**session_payload(session),'remaining_ms':remaining,'question_id':session.current_question_id,
            'participants':participants_payload(session),'stats':question_stats(session)}

# ---------------------------------------------------------------- отчёты
def results(code):
    room=get_room(code)
    if room is None: return None
    session=ensure_session(room)
    rows=[]
    for index,question in enumerate(room.questions.all()):
        rows.append({'question_id':question.id,'index':index+1,'text':question.text,
                     'correct_options':question.expected,'options':question.options,
                     **question_stats(session,question)})
    return {'room_code':room.room_code,'session_id':session.id,'status':session.status,
            'started_at':epoch(session.started_at),'finished_at':epoch(session.finished_at),
            'leaderboard':leaderboard(session),'questions':rows,
            'participants':participants_payload(session)}
