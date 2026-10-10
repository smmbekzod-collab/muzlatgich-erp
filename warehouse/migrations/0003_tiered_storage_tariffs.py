from django.db import migrations, models

TIERS=['tier_1_10','tier_11_15','tier_16_25','tier_26_30','tier_31_plus']

class Migration(migrations.Migration):
    dependencies=[('warehouse','0002_loginthrottle_operation_reversal_of_and_more')]
    operations=[
        migrations.AlterField(model_name='tariff',name='service',
            field=models.CharField(max_length=10,choices=[
                ('cooling','Sovutish (eski tarif)'),
                ('storage','Saqlama (eski tarif)'),
                ('tiered','Muddatga ko‘ra, so‘m/kg')]))
    ] + [
        migrations.AddField(model_name=model,name=field,field=models.DecimalField(max_digits=16,decimal_places=2,null=True,blank=True,verbose_name=title))
        for model in ['tariff','lot']
        for field,title in [
            ('tier_1_10','1–10 kun, so‘m/kg'),('tier_11_15','11–15 kun, so‘m/kg'),
            ('tier_16_25','16–25 kun, so‘m/kg'),('tier_26_30','26–30 kun, so‘m/kg'),
            ('tier_31_plus','31+ kun, so‘m/kg')]
    ]
