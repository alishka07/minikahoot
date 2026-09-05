from django.db import migrations,models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('game','0001_initial')]
    operations=[
        migrations.CreateModel(
            name='Answer',
            fields=[
                ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
                ('option_id',models.CharField(max_length=64)),
                ('is_correct',models.BooleanField(default=False)),
                ('points',models.PositiveIntegerField(default=0)),
                ('response_ms',models.PositiveIntegerField()),
                ('submitted_at',models.DateTimeField(auto_now_add=True)),
                ('participant',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='answers',to='game.participant')),
                ('question',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='answers',to='game.question')),
            ],
        ),
        migrations.AddConstraint(model_name='answer',constraint=models.UniqueConstraint(fields=('participant','question'),name='one_answer_per_question')),
    ]
