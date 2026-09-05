from .settings import *  # noqa: F403
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'test-db.sqlite3',  # noqa: F405
                      'TEST':{'NAME':BASE_DIR/'test-db.sqlite3'},'OPTIONS':{'timeout':30}}}
CHANNEL_LAYERS={'default':{'BACKEND':'channels.layers.InMemoryChannelLayer'}}
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}
QUIZ={**QUIZ,'COUNTDOWN_MS':300,'NEXT_LEAD_MS':200,'TICK_MS':200,'REVEAL_MS':400,'QUESTION_SECONDS':2}  # noqa: F405
