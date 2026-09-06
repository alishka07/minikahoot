import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.getenv('DJANGO_SECRET_KEY','dev-only-change-me')
DEBUG=os.getenv('DJANGO_DEBUG','1')=='1'
ALLOWED_HOSTS=os.getenv('DJANGO_ALLOWED_HOSTS','*').split(',')
INSTALLED_APPS=['daphne','django.contrib.contenttypes','django.contrib.auth','django.contrib.sessions','django.contrib.staticfiles','corsheaders','rest_framework','channels','game']
MIDDLEWARE=['corsheaders.middleware.CorsMiddleware','django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware']
ROOT_URLCONF='quiz.urls'; ASGI_APPLICATION='quiz.asgi.application'; STATIC_URL='static/'
CORS_ALLOWED_ORIGINS=os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:3000').split(',')
DATABASE_URL=os.getenv('DATABASE_URL')  # единая строка подключения (Neon, Supabase и т.п.), если задана - в приоритете
if os.getenv('DJANGO_DB','postgres')=='sqlite':
    DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'db.sqlite3','OPTIONS':{'timeout':20}}}
elif DATABASE_URL:
    from urllib.parse import parse_qs,urlparse
    _parsed=urlparse(DATABASE_URL)
    _sslmode=(parse_qs(_parsed.query).get('sslmode',['require'])[0])
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':_parsed.path.lstrip('/'),
        'USER':_parsed.username,'PASSWORD':_parsed.password,'HOST':_parsed.hostname,'PORT':_parsed.port or 5432,
        'CONN_MAX_AGE':int(os.getenv('POSTGRES_CONN_MAX_AGE','60')),'OPTIONS':{'sslmode':_sslmode}}}
else:
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('POSTGRES_DB','quiz'),'USER':os.getenv('POSTGRES_USER','quiz'),'PASSWORD':os.getenv('POSTGRES_PASSWORD','quiz'),'HOST':os.getenv('POSTGRES_HOST','localhost'),'PORT':os.getenv('POSTGRES_PORT','5432'),'CONN_MAX_AGE':int(os.getenv('POSTGRES_CONN_MAX_AGE','60'))}}
# Redis нужен только чтобы связать НЕСКОЛЬКО процессов между собой. Daphne на бесплатном
# хостинге работает одним процессом, поэтому по умолчанию держим и рассылку событий, и
# блокировку движка в памяти: без сетевого круга к чужому провайдеру на каждое событие и
# без целого класса ошибок с оборванными простаивающими соединениями.
# Задайте REDIS_URL - вернётся Redis. Это ОБЯЗАТЕЛЬНО, если воркеров больше одного:
# иначе игроки одной комнаты окажутся на разных процессах и перестанут видеть друг друга.
REDIS_URL=os.getenv('REDIS_URL','').strip()
if REDIS_URL:
    # Сетевой Redis (Upstash и подобные) закрывает простаивающие соединения со своей стороны.
    # Без health_check_interval первая же рассылка после паузы уходит в мёртвый сокет: лобби
    # не видит вошедшего игрока, а сокет ведущего отваливается. redis-py с этой настройкой
    # пингует соединение перед использованием и молча переподключается.
    # socket_timeout здесь ставить нельзя - channels-redis читает очередь блокирующим вызовом.
    REDIS_POOL={'health_check_interval':30,'socket_keepalive':True,'socket_connect_timeout':5}
    CHANNEL_LAYERS={'default':{'BACKEND':'channels_redis.core.RedisChannelLayer','CONFIG':{'hosts':[{'address':REDIS_URL,**REDIS_POOL}],'capacity':2000,'expiry':30}}}
    CACHES={'default':{'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':REDIS_URL,'OPTIONS':dict(REDIS_POOL)}}
else:
    CHANNEL_LAYERS={'default':{'BACKEND':'channels.layers.InMemoryChannelLayer','CONFIG':{'capacity':2000,'expiry':30}}}
    CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'quizo-engine'}}
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'; USE_TZ=True
REST_FRAMEWORK={'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.AllowAny']}

# Правила синхронной игры. Все тайминги считает сервер, клиенты только рисуют оставшееся время.
QUIZ={
    'QUESTION_SECONDS':int(os.getenv('QUIZ_QUESTION_SECONDS','10')),      # окно на ответ
    'COUNTDOWN_MS':int(os.getenv('QUIZ_COUNTDOWN_MS','3000')),            # задержка перед первым вопросом (3-2-1)
    'NEXT_LEAD_MS':int(os.getenv('QUIZ_NEXT_LEAD_MS','1500')),            # задержка перед следующим вопросом
    'REVEAL_MS':int(os.getenv('QUIZ_REVEAL_MS','6000')),                  # показ статистики при авто-режиме
    'AUTO_ADVANCE':os.getenv('QUIZ_AUTO_ADVANCE','0')=='1',               # сервер сам листает вопросы
    'GRACE_MS':int(os.getenv('QUIZ_GRACE_MS','750')),                     # запас на сетевую задержку ответа
    'TICK_MS':int(os.getenv('QUIZ_TICK_MS','1000')),                      # частота лайв-трансляции
    'HEARTBEAT_TIMEOUT_MS':int(os.getenv('QUIZ_HEARTBEAT_TIMEOUT_MS','25000')),
    'MAX_POINTS':int(os.getenv('QUIZ_MAX_POINTS','1000')),
    'MIN_RATIO':float(os.getenv('QUIZ_MIN_RATIO','0.5')),                 # доля очков за самый медленный верный ответ
    'REQUIRE_HOST_TOKEN':os.getenv('QUIZ_REQUIRE_HOST_TOKEN','0')=='1',
    'EVENT_FEED_LIMIT':int(os.getenv('QUIZ_EVENT_FEED_LIMIT','200')),
}
LOGGING={'version':1,'disable_existing_loggers':False,
    'handlers':{'console':{'class':'logging.StreamHandler'}},
    'root':{'handlers':['console'],'level':os.getenv('DJANGO_LOG_LEVEL','INFO')},
    'loggers':{'game':{'handlers':['console'],'level':os.getenv('QUIZ_LOG_LEVEL','INFO'),'propagate':False}}}
