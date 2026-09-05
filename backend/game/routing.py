from django.urls import re_path
from .consumers import QuizConsumer
websocket_urlpatterns=[re_path(r'^ws/quiz/(?P<room_code>\d{6})/$',QuizConsumer.as_asgi())]
