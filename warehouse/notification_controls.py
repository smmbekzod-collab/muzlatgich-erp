"""Platform-wide notification flags. A pause prevents DB report generation and Bot API calls.

Railway cron processes may still start; disable their schedules in Railway to
avoid invocation costs entirely. Do not couple this to a Railway API secret.
"""
from django.db import transaction
from .models import PlatformNotificationControl,DailyTelegramDigest,CameraEnvironmentAlert


def current_controls():
    return PlatformNotificationControl.objects.get_or_create(pk=1)[0]


def is_enabled(kind):
    setting=current_controls()
    if kind=='reports':return setting.reports_enabled
    if kind=='alerts':return setting.alerts_enabled
    raise ValueError('Unknown notification kind')


@transaction.atomic
def set_enabled(kind,enabled,user):
    if not user.is_active or not user.is_superuser:
        raise PermissionError('Only platform super admins may change delivery')
    flag={'reports':'reports_enabled','alerts':'alerts_enabled'}.get(kind)
    if not flag:raise ValueError('Unknown notification kind')
    controls=current_controls()
    controls=PlatformNotificationControl.objects.select_for_update().get(pk=1)
    setattr(controls,flag,enabled)
    controls.updated_by=user
    controls.save(update_fields=[flag,'updated_by','updated_at'])
    if not enabled:
        if kind=='reports':
            DailyTelegramDigest.objects.filter(delivery_status__in=['pending','failed']).update(
                delivery_status='disabled',next_attempt_at=None,claimed_at=None,
                last_error='Super Admin hisobotlarni vaqtincha to‘xtatdi')
        else:
            CameraEnvironmentAlert.objects.filter(delivery_status__in=['pending','failed']).update(
                delivery_status='disabled',next_attempt_at=None,claimed_at=None,
                last_error='Super Admin ogohlantirishlarni vaqtincha to‘xtatdi')
    return controls
