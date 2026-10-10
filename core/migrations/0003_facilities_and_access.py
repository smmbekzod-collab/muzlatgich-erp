# Generated for Muzlatgich ERP 2.0; preserves every existing camera and lot.
import django.db.models.deletion
from django.db import migrations, models

def backfill_main_facility(apps, schema_editor):
    Organization = apps.get_model('core','Organization')
    Facility = apps.get_model('core','Facility')
    Camera = apps.get_model('core','Camera')
    alias = schema_editor.connection.alias
    for org in Organization.objects.using(alias).all().iterator():
        facility, _ = Facility.objects.using(alias).get_or_create(
            organization_id=org.pk, code='main', defaults={'name':'Asosiy ombor'})
        Camera.objects.using(alias).filter(organization_id=org.pk, facility_id__isnull=True).update(facility_id=facility.pk)

def keep_existing_facilities(apps, schema_editor):
    # Reversing schema should never erase existing organizational data.
    pass

class Migration(migrations.Migration):
    dependencies = [('core','0002_membership_can_manage_expenses')]
    operations = [
        migrations.CreateModel(
            name='Facility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=80, verbose_name='Filial kodi')),
                ('name', models.CharField(max_length=160, verbose_name='Filial / ombor nomi')),
                ('region', models.CharField(blank=True, max_length=120, verbose_name='Viloyat')),
                ('district', models.CharField(blank=True, max_length=120, verbose_name='Tuman / shahar')),
                ('address', models.CharField(blank=True, max_length=250, verbose_name='Manzil')),
                ('is_active', models.BooleanField(default=True, verbose_name='Faol')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='facilities', to='core.organization', verbose_name='Tashkilot')),
            ],
            options={'verbose_name':'Filial / ombor','verbose_name_plural':'Filiallar / omborlar','ordering':['organization_id','name']},
        ),
        migrations.AddConstraint(model_name='facility', constraint=models.UniqueConstraint(fields=('organization','code'), name='unique_facility_code_per_org')),
        migrations.AddField(model_name='camera', name='facility', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cameras', to='core.facility', verbose_name='Filial / ombor')),
        migrations.AddField(model_name='membership', name='all_facilities', field=models.BooleanField(default=True, verbose_name='Barcha filiallar')),
        migrations.AddField(model_name='membership', name='facilities', field=models.ManyToManyField(blank=True, to='core.facility', verbose_name='Ruxsat berilgan filiallar')),
        migrations.AlterModelOptions(name='camera', options={'ordering':['organization_id','facility_id','number'],'verbose_name':'Muzlatgich kamerasi','verbose_name_plural':'Muzlatgich kameralari'}),
        migrations.RunPython(backfill_main_facility, keep_existing_facilities),
        migrations.RemoveConstraint(model_name='camera', name='unique_camera_number_per_org'),
        migrations.AddConstraint(model_name='camera', constraint=models.UniqueConstraint(fields=('organization','facility','number'), name='unique_camera_number_per_facility')),
    ]
