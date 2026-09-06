"""Игровой движок: единый серверный таймер комнаты.

Задача - чтобы вопрос открылся и закрылся у всех одновременно, независимо от того,
кто когда нажал кнопку и у кого какой пинг. Движок не привязан к соединению хоста:
это отдельная asyncio-задача, которая читает дедлайны из БД и рассылает события в группу.
Между процессами задачу защищает Redis-блокировка, поэтому тикает ровно один воркер.
"""
import asyncio,logging,time,uuid
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from . import services
from .models import GameSession as S

log=logging.getLogger('game')
WORKER=uuid.uuid4().hex
LOCK_TTL=15
REFRESH_EVERY=5  # секунд между продлениями блокировки - с большим запасом от LOCK_TTL
_tasks={}
_wakeups={}

def group_of(code): return f'quiz_{code}'

def _wakeup(code):
    event=_wakeups.get(code)
    if event is None: event=_wakeups[code]=asyncio.Event()
    return event

def nudge(code):
    """Разбудить цикл комнаты немедленно - например, когда ответил последний игрок."""
    _wakeup(code).set()

async def _sleep(code,seconds):
    """Сон, прерываемый nudge(). Решение по-прежнему принимает сам цикл."""
    event=_wakeup(code)
    try: await asyncio.wait_for(event.wait(),timeout=seconds)
    except asyncio.TimeoutError: pass
    event.clear()
def cfg(key): return settings.QUIZ[key]

# ------------------------------------------------------------------ блокировка воркера
@database_sync_to_async
def _state(code): return services.engine_state(code)
_open=database_sync_to_async(services.open_question)
_close=database_sync_to_async(services.close_question)
_advance=database_sync_to_async(services.advance)
_frame=database_sync_to_async(services.live_frame)
_snapshot=database_sync_to_async(services.snapshot)

async def frame_snapshot(code): return await _snapshot(code,host=True,events=False)

def _acquire_sync(code): return cache.add(f'engine:{code}',WORKER,timeout=LOCK_TTL)
def _refresh_sync(code):
    if cache.get(f'engine:{code}') not in (WORKER,None): return False
    cache.set(f'engine:{code}',WORKER,timeout=LOCK_TTL); return True
def _release_sync(code):
    if cache.get(f'engine:{code}')==WORKER: cache.delete(f'engine:{code}')

# Django-кэш - синхронный клиент; на реальном сетевом Redis (не localhost) один такой вызов
# может занимать 100+ мс. Без sync_to_async это блокирует весь event loop сервера на это время
# при КАЖДОМ обращении - выносим в пул потоков, чтобы не подвешивать остальные комнаты и сокеты.
_acquire=sync_to_async(_acquire_sync,thread_sensitive=False)
_refresh=sync_to_async(_refresh_sync,thread_sensitive=False)
_release=sync_to_async(_release_sync,thread_sensitive=False)

async def send(code,message):
    await get_channel_layer().group_send(group_of(code),message)

def ensure(code):
    """Запустить (или перезапустить) цикл комнаты. Идемпотентно."""
    task=_tasks.get(code)
    if task is not None and not task.done(): return task
    task=asyncio.create_task(run(code),name=f'quiz-engine-{code}')
    _tasks[code]=task
    task.add_done_callback(lambda done: _tasks.pop(code,None) if _tasks.get(code) is done else None)
    return task

async def stop(code):
    task=_tasks.pop(code,None)
    if task is not None and not task.done():
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

async def run(code):
    if not await _acquire(code):
        log.debug('engine %s: комнату ведёт другой воркер',code); return
    log.info('engine %s: старт цикла',code)
    last_refresh=time.time()
    try:
        while True:
            state=await _state(code)
            if state is None or state['status'] in (S.LOBBY,S.FINISHED): break
            moment=time.time()
            if state['status']==S.COUNTDOWN:
                if state['starts_at'] is None or moment>=state['starts_at']:
                    await open_now(code); continue
                await _sleep(code,min(0.2,max(0.01,state['starts_at']-moment)))
            elif state['status']==S.QUESTION:
                deadline=(state['ends_at'] or moment)+cfg('GRACE_MS')/1000
                if moment>=deadline or state['all_answered']:
                    await close_now(code); continue
                await broadcast_tick(code)
                await _sleep(code,min(cfg('TICK_MS')/1000,max(0.05,deadline-time.time())))
            else:  # reveal
                if not state['auto_advance']: break  # дальше решает хост, он же перезапустит цикл
                if state['reveal_ends_at'] is None or moment>=state['reveal_ends_at']:
                    await advance_now(code); continue
                await _sleep(code,min(0.2,max(0.01,state['reveal_ends_at']-moment)))
            if moment-last_refresh>=REFRESH_EVERY:
                if not await _refresh(code): log.warning('engine %s: потеряна блокировка',code); break
                last_refresh=moment
    except asyncio.CancelledError: raise
    except Exception:
        log.exception('engine %s: цикл упал',code)
    finally:
        _wakeups.pop(code,None)
        await _release(code)
        log.info('engine %s: цикл остановлен',code)

# ------------------------------------------------------------------ переходы с рассылкой
async def open_now(code):
    session=await _open(code)
    if session is None: return
    payload=await frame_snapshot(code)
    await send(code,{'type':'game.question','payload':payload})

async def close_now(code,forced=False):
    session,stats=await _close(code,forced)
    if session is None: return
    payload=await frame_snapshot(code)
    await send(code,{'type':'game.closed','payload':payload,'stats':stats})

async def advance_now(code,question_id=None):
    session,finished=await _advance(code,question_id)
    if session is None: return None,False
    payload=await frame_snapshot(code)
    if finished: await send(code,{'type':'game.finished','payload':payload})
    else:
        await send(code,{'type':'game.countdown','payload':payload})
        ensure(code)
    return session,finished

async def broadcast_tick(code):
    frame=await _frame(code)
    if frame is not None: await send(code,{'type':'game.tick','frame':frame})
