from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('warehouse', '0011_iot_hub'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cameraenvironmentpolicy', name='profile_code',
            field=models.CharField(
                verbose_name='Saqlanadigan mahsulot rejimi', max_length=24, default='', blank=True,
                choices=[
                    ('', 'Qo‘lda sozlash'), ('grape','Uzum'), ('carrot','Sabzi'),
                    ('potato','Kartoshka (iste’mol)'), ('potato_processing','Kartoshka (qayta ishlash)'),
                    ('onion_dry','Piyoz (quruq)'),
                ],
            ),
        ),
        migrations.CreateModel(
            name='CameraEnvironmentProfileChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previous_profile', models.CharField(max_length=24, blank=True, default='')),
                ('current_profile', models.CharField(max_length=24, blank=True, default='')),
                ('previous_limits', models.JSONField(default=dict)),
                ('current_limits', models.JSONField(default=dict)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('camera', models.ForeignKey(
                    to='core.camera', related_name='environment_profile_changes',
                    on_delete=django.db.models.deletion.PROTECT)),
                ('changed_by', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
            ],
            options={'ordering':['-changed_at','-pk']},
        ),
    ]
