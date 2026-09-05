from django.conf import settings
from rest_framework import serializers
from .models import GameEvent,GameSession,Participant,Question,Room

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model=Question
        fields=['id','room','order','text','options','correct_option','correct_options','is_multiple','image','duration_seconds','max_points']
        extra_kwargs={'room':{'required':False},'order':{'required':False},
                      'correct_option':{'write_only':True},'correct_options':{'write_only':True}}
    def validate_options(self,value):
        ids=[str(option.get('id')) for option in value if isinstance(option,dict)]
        if len(ids)<2: raise serializers.ValidationError('Нужно минимум два варианта ответа.')
        if len(ids)!=len(set(ids)): raise serializers.ValidationError('Идентификаторы вариантов должны быть уникальными.')
        return value
    def validate_duration_seconds(self,value):
        if not 3<=value<=300: raise serializers.ValidationError('Длительность вопроса: от 3 до 300 секунд.')
        return value
    def validate(self,data):
        options=data.get('options',getattr(self.instance,'options',[]) or [])
        option_ids={str(option.get('id')) for option in options if isinstance(option,dict)}
        raw=data.get('correct_options') or ([data.get('correct_option')] if data.get('correct_option') else [])
        correct=[str(value) for value in raw if value is not None]
        if not correct or not set(correct).issubset(option_ids):
            raise serializers.ValidationError('Каждый правильный вариант должен быть среди options.')
        if not data.get('is_multiple',getattr(self.instance,'is_multiple',False)) and len(correct)!=1:
            raise serializers.ValidationError('У вопроса с одним ответом должен быть ровно один правильный вариант.')
        data['correct_options']=correct
        data['correct_option']=correct[0]
        data.setdefault('duration_seconds',settings.QUIZ['QUESTION_SECONDS'])
        return data

class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model=Participant
        fields=['id','name','score','is_online','stage','current_index','last_seen_at','joined_at']
        read_only_fields=fields

class GameSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model=GameSession
        fields=['id','status','current_index','current_question','question_order','starts_at','ends_at',
                'reveal_ends_at','auto_advance','started_at','finished_at','created_at']
        read_only_fields=fields

class GameEventSerializer(serializers.ModelSerializer):
    class Meta:
        model=GameEvent
        fields=['id','kind','participant','question','payload','created_at']
        read_only_fields=fields

class RoomSerializer(serializers.ModelSerializer):
    questions=QuestionSerializer(many=True,read_only=True)
    session=GameSessionSerializer(read_only=True)
    class Meta:
        model=Room
        fields=['id','room_code','title','host_token','is_active','created_at','questions','session']
        read_only_fields=['room_code','host_token','created_at']
    def to_representation(self,instance):
        data=super().to_representation(instance)
        if not self.context.get('reveal_token'): data.pop('host_token',None)  # токен отдаём только создателю комнаты
        return data
