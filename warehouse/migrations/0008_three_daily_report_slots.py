from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('warehouse','0007_daily_telegram_digests')]

    operations = [
        migrations.AlterField(
            model_name='telegramalertdestination',
            name='daily_digest_enabled',
            field=models.BooleanField(default=True,
                verbose_name='Hisobotlar 08:00, 14:00, 20:00')),
        migrations.AddField(
            model_name='dailytelegramdigest',
            name='slot_hour',
            field=models.PositiveSmallIntegerField(
                choices=[(8,'08:00'),(14,'14:00'),(20,'20:00')],
                default=8,
                verbose_name='Hisobot soati'),
            preserve_default=False,
        ),
        migrations.RemoveConstraint(
            model_name='dailytelegramdigest',
            name='unique_daily_digest_per_org',
        ),
        migrations.AddConstraint(
            model_name='dailytelegramdigest',
            constraint=models.UniqueConstraint(
                fields=['organization','report_date','slot_hour'],
                name='unique_daily_digest_per_org'),
        ),
    ]
