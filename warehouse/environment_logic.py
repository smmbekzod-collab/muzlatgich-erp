"""Evaluation is a deterministic comparison against settings approved by the organization.
No claim of product safety, predictive analytics, or live IoT feed.
"""
from datetime import timedelta
from django.utils import timezone


def assess_camera(camera, policy, reading, oldest_received, now=None):
    now = now or timezone.now()
    result = {
        'camera':camera, 'policy':policy,'reading':reading,
        'state':'unknown','label':'Me’yor belgilanmagan',
        'issues':[],'storage_days':None,'days_warning':False,
    }
    if oldest_received:
        count=max(1,(timezone.localtime(now).date()-oldest_received).days+1)
        result['storage_days']=count
        if policy and policy.max_storage_days is not None and count > policy.max_storage_days:
            result['issues'].append(f'Eng eski partiya belgilangan {policy.max_storage_days} kunlik nazorat chegarasidan oshgan')
            result['days_warning']=True
    if not reading:
        result['label']='O‘lchov kiritilmagan'
        result['state']='missing'
        return result

    if policy is None:
        result['label']='Me’yor sozlanmagan'
        return result

    values = (
        ('min_temperature', 'Harorat belgilangan pastki chegaradan tushgan',
         lambda value,limit: value<limit),
        ('max_temperature', 'Harorat belgilangan yuqori chegaradan oshgan',
         lambda value,limit: value>limit),
        ('min_humidity', 'Namlik belgilangan pastki chegaradan tushgan',
         lambda value,limit: value<limit),
        ('max_humidity', 'Namlik belgilangan yuqori chegaradan oshgan',
         lambda value,limit: value>limit),
    )
    for field, note, failed in values:
        limit=getattr(policy,field)
        value=reading.temperature if field.endswith('temperature') else reading.humidity
        if limit is not None and failed(value,limit):
            result['issues'].append(note)

    age=now-reading.measured_at
    if age > timedelta(hours=policy.check_interval_hours):
        result['issues'].append(f'O‘lchov {policy.check_interval_hours} soatlik tekshiruv oralig‘idan eskirgan')

    if result['issues']:
        result['label']='E’tibor talab etiladi'
        result['state']='alert'
    elif any(getattr(policy,f) is not None for f in
            ('min_temperature','max_temperature','min_humidity','max_humidity')):
        result['label']='Kiritilgan chegaralarda'
        result['state']='good'
    else:
        result['label']='Harorat/namlik me’yori belgilanmagan'
        result['state']='unknown'
    return result
