from rest_framework import status,viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound,PermissionDenied,ValidationError
from rest_framework.response import Response
from . import services
from .models import Question,Room
from .serializers import QuestionSerializer,RoomSerializer

class RoomViewSet(viewsets.ModelViewSet):
    queryset=Room.objects.all().order_by('-created_at')
    serializer_class=RoomSerializer
    lookup_field='room_code'
    lookup_value_regex=r'\d{6}'

    def get_serializer_context(self):
        context=super().get_serializer_context()
        context['reveal_token']=self.action=='create' or self._token_ok()
        return context

    def _token_ok(self):
        token=self.request.query_params.get('token') or self.request.headers.get('X-Host-Token')
        code=self.kwargs.get('room_code')
        return bool(code and token and services.is_host_token(code,token))

    def _require_host(self):
        if not self._token_ok(): raise PermissionDenied('Нужен токен ведущего.')

    @action(detail=True,methods=['get'])
    def state(self,request,room_code=None):
        """Текущее состояние комнаты: статус, дедлайны, участники, живая статистика."""
        payload=services.snapshot(room_code,host=self._token_ok())
        if payload is None: raise NotFound('Комната не найдена.')
        return Response(payload)

    @action(detail=True,methods=['get'])
    def results(self,request,room_code=None):
        """Итоги: рейтинг, распределение ответов и время реакции по каждому вопросу."""
        payload=services.results(room_code)
        if payload is None: raise NotFound('Комната не найдена.')
        return Response(payload)

    @action(detail=True,methods=['get'])
    def events(self,request,room_code=None):
        """Лента действий: кто зашёл, вышел, ответил и когда. ?after=<id> - только новые."""
        room=services.get_room(room_code)
        if room is None: raise NotFound('Комната не найдена.')
        session=services.ensure_session(room)
        after=request.query_params.get('after')
        limit=min(int(request.query_params.get('limit') or 200),500)
        rows=services.recent_events(session,limit=limit,after_id=int(after) if after and after.isdigit() else None)
        return Response({'session_id':session.id,'events':rows,'server_time':services.now_ms()})

    @action(detail=True,methods=['post'])
    def close(self,request,room_code=None):
        self._require_host()
        room=services.get_room(room_code)
        if room is None: raise NotFound('Комната не найдена.')
        room.is_active=False
        room.save(update_fields=['is_active'])
        return Response({'room_code':room.room_code,'is_active':False},status=status.HTTP_200_OK)

class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class=QuestionSerializer

    def get_queryset(self): return Question.objects.filter(room__room_code=self.kwargs['room_code'])

    def get_serializer(self,*args,**kwargs):
        if isinstance(kwargs.get('data'),list): kwargs['many']=True  # разрешаем создать пачку вопросов одним запросом
        return super().get_serializer(*args,**kwargs)

    def _room(self):
        room=Room.objects.filter(room_code=self.kwargs['room_code'],is_active=True).first()
        if room is None: raise ValidationError('Активная комната не найдена.')
        return room

    def perform_create(self,serializer): serializer.save(room=self._room())
