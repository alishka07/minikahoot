from django.db import migrations,models

def copy_existing_answers(apps,schema_editor):
    Question=apps.get_model('game','Question')
    Answer=apps.get_model('game','Answer')
    for question in Question.objects.all().iterator():
        question.correct_options=[question.correct_option]
        question.save(update_fields=['correct_options'])
    for answer in Answer.objects.all().iterator():
        answer.option_ids=[answer.option_id] if answer.option_id else []
        answer.save(update_fields=['option_ids'])

class Migration(migrations.Migration):
    dependencies=[('game','0002_answer')]
    operations=[
        migrations.AddField(model_name='question',name='correct_options',field=models.JSONField(blank=True,default=list)),
        migrations.AddField(model_name='question',name='is_multiple',field=models.BooleanField(default=False)),
        migrations.AddField(model_name='question',name='image',field=models.TextField(blank=True,default='')),
        migrations.AddField(model_name='answer',name='option_ids',field=models.JSONField(default=list)),
        migrations.RunPython(copy_existing_answers,migrations.RunPython.noop),
    ]
