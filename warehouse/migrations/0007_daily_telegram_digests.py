import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('warehouse','0006_telegram_monitoring_alerts')]

    operations = [
        migrations.AddField(
            model_name='telegramalertdestination',
            name='daily_digest_enabled',
            field=models.BooleanField(default=True,verbose_name='Hisobotlar 08:00, 14:00, 20:00')),
        migrations.AddConstraint(
            model_name='telegramalertdestination',
            constraint=models.UniqueConstraint(fields=['chat_id'],
                condition=Q(enabled=True),name='unique_active_telegram_chat')),
        migrations.CreateModel(name='DailyTelegramDigest',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('report_date',models.DateField(verbose_name='Hisobot sanasi')),
            ('slot_hour',models.PositiveSmallIntegerField(choices=[(8,'08:00'),(14,'14:00'),(20,'20:00')],verbose_name='Hisobot soati')),
            ('message',models.TextField(verbose_name='Tashkilotning kunlik hisoboti')),
            ('delivery_status',models.CharField(max_length=12,default='pending',choices=[
                ('pending','Navbatda'),('sending','Yuborilmoqda'),
                ('sent','Yuborilgan'),('failed','Xatolik'),('disabled','To‘xtatilgan')])),
            ('chat_id',models.CharField(blank=True,max_length=32,verbose_name='Oxirgi yo‘naltirilgan chat')),
            ('attempts',models.PositiveSmallIntegerField(default=0)),
            ('next_attempt_at',models.DateTimeField(blank=True,null=True)),
            ('claimed_at',models.DateTimeField(blank=True,null=True)),
            ('sent_at',models.DateTimeField(blank=True,null=True)),
            ('last_error',models.CharField(blank=True,max_length=120)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('organization',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                related_name='daily_telegram_digests',to='core.organization')),
        ],options={'ordering':['-report_date','-pk']}),
        migrations.AddConstraint(model_name='dailytelegramdigest',
            constraint=models.UniqueConstraint(fields=['organization','report_date','slot_hour'],
                name='unique_daily_digest_per_org')),
        migrations.AddIndex(model_name='dailytelegramdigest',
            index=models.Index(fields=['delivery_status','next_attempt_at'],name='daily_digest_queue_idx')),
    ]
