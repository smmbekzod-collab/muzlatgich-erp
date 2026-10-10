from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0003_facilities_and_access')]
    operations = [
        migrations.AddField(
            model_name='membership',
            name='can_monitor_environment',
            field=models.BooleanField(default=False, verbose_name='Harorat va namlik qayd etish'),
        ),
    ]
