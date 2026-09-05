import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','quiz.settings')
from django.core.asgi import get_asgi_application
django_application=get_asgi_application()  # вызывает django.setup() до импорта моделей — иначе daphne не стартует
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter,URLRouter
from game.routing import websocket_urlpatterns
application=ProtocolTypeRouter({'http':django_application,'websocket':AuthMiddlewareStack(URLRouter(websocket_urlpatterns))})
