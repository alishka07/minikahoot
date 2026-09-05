import django.db.models.deletion,django.utils.timezone,game.models
from django.db import migrations,models

def backfill(apps,schema_editor):
    """Заводим по сессии на каждую существующую комнату и привязываем к ней старые данные."""
    Room=apps.get_model('game','Room')
    GameSession=apps.get_model('game','GameSession')
    Question=apps.get_model('game','Question')
    Participant=apps.get_model('game','Participant')
    Answer=apps.get_model('game','Answer')
    for room in Room.objects.all().iterator():
        room.host_token=game.models.make_token()
        room.save(update_fields=['host_token'])
        ids=list(Question.objects.filter(room=room).order_by('id').values_list('id',flat=True))
        for position,question_id in enumerate(ids,start=1):
            Question.objects.filter(id=question_id).update(order=position)
        answers=Answer.objects.filter(participant__room=room)
        session=GameSession.objects.create(room=room,question_order=ids,
                                           status='finished' if answers.exists() else 'lobby',
                                           current_index=0)
        Participant.objects.filter(room=room).update(session=session)
        for participant in Participant.objects.filter(room=room).iterator():
            participant.token=game.models.make_token()
            participant.save(update_fields=['token'])
        answers.update(session=session)

def unbackfill(apps,schema_editor):
    apps.get_model('game','Answer').objects.update(session=None)
    apps.get_model('game','Participant').objects.update(session=None)

class Migration(migrations.Migration):
    dependencies=[('game','0003_multiple_choice_and_images')]
    operations=[
        migrations.CreateModel(
            name='GameSession',
            fields=[
                ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
                ('status',models.CharField(choices=[('lobby','lobby'),('countdown','countdown'),('question','question'),('reveal','reveal'),('finished','finished')],default='lobby',max_length=16)),
                ('current_index',models.PositiveIntegerField(default=0)),
                ('question_order',models.JSONField(blank=True,default=list)),
                ('starts_at',models.DateTimeField(blank=True,null=True)),
                ('ends_at',models.DateTimeField(blank=True,null=True)),
                ('reveal_ends_at',models.DateTimeField(blank=True,null=True)),
                ('auto_advance',models.BooleanField(default=False)),
                ('started_at',models.DateTimeField(blank=True,null=True)),
                ('finished_at',models.DateTimeField(blank=True,null=True)),
                ('created_at',models.DateTimeField(auto_now_add=True)),
                ('current_question',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='+',to='game.question')),
                ('room',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='sessions',to='game.room')),
            ],
            options={'ordering':['-id']},
        ),
        migrations.AddField(model_name='room',name='title',field=models.CharField(blank=True,default='',max_length=120)),
        migrations.AddField(model_name='room',name='host_token',field=models.CharField(default=game.models.make_token,editable=False,max_length=32)),
        migrations.AddField(model_name='question',name='order',field=models.PositiveIntegerField(db_index=True,default=0)),
        migrations.AddField(model_name='question',name='duration_seconds',field=models.PositiveIntegerField(default=10)),
        migrations.AddField(model_name='question',name='max_points',field=models.PositiveIntegerField(default=1000)),
        migrations.AlterModelOptions(name='question',options={'ordering':['order','id']}),
        migrations.AddField(model_name='participant',name='session',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='participants',to='game.gamesession')),
        migrations.AddField(model_name='participant',name='token',field=models.CharField(db_index=True,default=game.models.make_token,editable=False,max_length=32)),
        migrations.AddField(model_name='participant',name='connections',field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='participant',name='stage',field=models.CharField(choices=[('waiting','waiting'),('playing','playing'),('answered','answered'),('finished','finished')],default='waiting',max_length=16)),
        migrations.AddField(model_name='participant',name='current_index',field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='participant',name='current_question',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='+',to='game.question')),
        migrations.AddField(model_name='participant',name='last_seen_at',field=models.DateTimeField(default=django.utils.timezone.now)),
        migrations.AddField(model_name='participant',name='joined_at',field=models.DateTimeField(auto_now_add=True,default=django.utils.timezone.now),preserve_default=False),
        migrations.AlterModelOptions(name='participant',options={'ordering':['-score','name']}),
        migrations.RemoveConstraint(model_name='answer',name='one_answer_per_question'),
        migrations.AddField(model_name='answer',name='session',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,related_name='answers',to='game.gamesession')),
        migrations.AlterModelOptions(name='answer',options={'ordering':['response_ms','id']}),
        migrations.CreateModel(
            name='GameEvent',
            fields=[
                ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
                ('kind',models.CharField(db_index=True,max_length=24)),
                ('payload',models.JSONField(blank=True,default=dict)),
                ('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),
                ('participant',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='events',to='game.participant')),
                ('question',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='+',to='game.question')),
                ('session',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='events',to='game.gamesession')),
            ],
            options={'ordering':['id']},
        ),
        migrations.RunPython(backfill,unbackfill),
        migrations.AddConstraint(model_name='answer',constraint=models.UniqueConstraint(fields=('session','participant','question'),name='one_answer_per_question')),
    ]
