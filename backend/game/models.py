import secrets,uuid
from django.db import models
from django.utils import timezone

def room_code(): return ''.join(str(secrets.randbelow(10)) for _ in range(6))
def make_token(): return uuid.uuid4().hex

class Room(models.Model):
    room_code=models.CharField(max_length=6,unique=True,default=room_code)
    title=models.CharField(max_length=120,blank=True,default='')
    host_token=models.CharField(max_length=32,default=make_token,editable=False)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.room_code
    @property
    def session(self):
        """Текущая (последняя) сессия комнаты."""
        return self.sessions.order_by('-id').first()

class Question(models.Model):
    room=models.ForeignKey(Room,related_name='questions',on_delete=models.CASCADE)
    order=models.PositiveIntegerField(default=0,db_index=True)
    text=models.TextField()
    options=models.JSONField(default=list,help_text='[{"id":"a","text":"Answer"}]')
    correct_option=models.CharField(max_length=64)
    correct_options=models.JSONField(default=list,blank=True)
    is_multiple=models.BooleanField(default=False)
    image=models.TextField(blank=True,default='')
    duration_seconds=models.PositiveIntegerField(default=10)
    max_points=models.PositiveIntegerField(default=1000)
    class Meta: ordering=['order','id']
    def __str__(self): return f'{self.room_id}#{self.order} {self.text[:24]}'
    @property
    def expected(self): return [str(value) for value in (self.correct_options or ([self.correct_option] if self.correct_option else []))]
    def clean(self):
        from django.core.exceptions import ValidationError
        ids=[str(option.get('id')) for option in self.options if isinstance(option,dict)]
        if len(ids)<2 or len(ids)!=len(set(ids)) or self.correct_option not in ids: raise ValidationError('Options need unique ids and must contain correct_option.')
    def save(self,*args,**kwargs):
        if not self.order and self.room_id:
            self.order=(Question.objects.filter(room_id=self.room_id).exclude(pk=self.pk).aggregate(models.Max('order'))['order__max'] or 0)+1
        super().save(*args,**kwargs)

class GameSession(models.Model):
    """Один прогон викторины. Хранит серверные дедлайны — источник правды для таймера."""
    LOBBY,COUNTDOWN,QUESTION,REVEAL,FINISHED='lobby','countdown','question','reveal','finished'
    STATUSES=[(LOBBY,'lobby'),(COUNTDOWN,'countdown'),(QUESTION,'question'),(REVEAL,'reveal'),(FINISHED,'finished')]
    room=models.ForeignKey(Room,related_name='sessions',on_delete=models.CASCADE)
    status=models.CharField(max_length=16,choices=STATUSES,default=LOBBY)
    current_question=models.ForeignKey(Question,null=True,blank=True,on_delete=models.SET_NULL,related_name='+')
    current_index=models.PositiveIntegerField(default=0)
    question_order=models.JSONField(default=list,blank=True)
    starts_at=models.DateTimeField(null=True,blank=True)
    ends_at=models.DateTimeField(null=True,blank=True)
    reveal_ends_at=models.DateTimeField(null=True,blank=True)
    auto_advance=models.BooleanField(default=False)
    started_at=models.DateTimeField(null=True,blank=True)
    finished_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-id']
    def __str__(self): return f'{self.room.room_code}/{self.id} {self.status}'
    @property
    def total(self): return len(self.question_order)
    @property
    def is_live(self): return self.status in (self.COUNTDOWN,self.QUESTION,self.REVEAL)

class Participant(models.Model):
    WAITING,PLAYING,ANSWERED,FINISHED='waiting','playing','answered','finished'
    STAGES=[(WAITING,'waiting'),(PLAYING,'playing'),(ANSWERED,'answered'),(FINISHED,'finished')]
    room=models.ForeignKey(Room,related_name='participants',on_delete=models.CASCADE)
    session=models.ForeignKey(GameSession,null=True,blank=True,related_name='participants',on_delete=models.SET_NULL)
    name=models.CharField(max_length=32)
    token=models.CharField(max_length=32,default=make_token,editable=False,db_index=True)
    score=models.PositiveIntegerField(default=0)
    is_online=models.BooleanField(default=True)
    connections=models.PositiveIntegerField(default=0)
    stage=models.CharField(max_length=16,choices=STAGES,default=WAITING)
    current_index=models.PositiveIntegerField(default=0)
    current_question=models.ForeignKey(Question,null=True,blank=True,on_delete=models.SET_NULL,related_name='+')
    last_seen_at=models.DateTimeField(default=timezone.now)
    joined_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['room','name'],name='unique_name_per_room')]
        ordering=['-score','name']
    def __str__(self): return f'{self.name}@{self.room_id}'

class Answer(models.Model):
    session=models.ForeignKey(GameSession,null=True,blank=True,related_name='answers',on_delete=models.CASCADE)
    participant=models.ForeignKey(Participant,related_name='answers',on_delete=models.CASCADE)
    question=models.ForeignKey(Question,related_name='answers',on_delete=models.CASCADE)
    option_id=models.CharField(max_length=64)
    option_ids=models.JSONField(default=list)
    is_correct=models.BooleanField(default=False)
    points=models.PositiveIntegerField(default=0)
    response_ms=models.PositiveIntegerField()
    submitted_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['session','participant','question'],name='one_answer_per_question')]
        ordering=['response_ms','id']

class GameEvent(models.Model):
    """Лента живых событий: кто зашёл, вышел, ответил, какой вопрос открылся."""
    JOINED,LEFT,REJOINED='joined','left','rejoined'
    ANSWERED,QUESTION_OPENED,QUESTION_CLOSED='answered','question_opened','question_closed'
    GAME_STARTED,GAME_FINISHED='game_started','game_finished'
    session=models.ForeignKey(GameSession,related_name='events',on_delete=models.CASCADE)
    kind=models.CharField(max_length=24,db_index=True)
    participant=models.ForeignKey(Participant,null=True,blank=True,on_delete=models.SET_NULL,related_name='events')
    question=models.ForeignKey(Question,null=True,blank=True,on_delete=models.SET_NULL,related_name='+')
    payload=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True,db_index=True)
    class Meta: ordering=['id']
    def as_dict(self):
        return {'id':self.id,'kind':self.kind,'participant_id':self.participant_id,'name':self.payload.get('name'),
                'question_id':self.question_id,'at':self.created_at.timestamp()*1000,**self.payload}
