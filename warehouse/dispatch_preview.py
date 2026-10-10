"""Signed and expiring confirmation for dispatch; no database writes in preview."""
from datetime import date, datetime
from decimal import Decimal
from django.core import signing
from django.core.exceptions import ValidationError
from .services import dispatch_snapshot

SALT = 'warehouse.dispatch.preview.v1'
AGE_SECONDS = 15 * 60
CONFIRM_FIELDS = ('request_key', 'date', 'boxes', 'gross', 'tare',
                  'payment', 'payment_method', 'note')

def normalized_fields(data):
    canonical = {}
    for key in CONFIRM_FIELDS:
        val = data.get(key)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = str(val)
        canonical[key] = '' if val is None else str(val)
    return canonical

def make_dispatch_token(user, lot, data):
    payload = {
        'user':user.pk,
        'lot':str(lot.pk),
        'form':normalized_fields(data),
        'snapshot':dispatch_snapshot(lot),
    }
    return signing.dumps(payload, salt=SALT, compress=True)

def verify_dispatch_token(user, lot, data, token):
    if not token:
        raise ValidationError('Avval xizmat haqini hisoblab ko‘ring, keyin tasdiqlang.')
    try:
        payload = signing.loads(token, salt=SALT, max_age=AGE_SECONDS)
    except (signing.BadSignature, signing.SignatureExpired, ValueError, TypeError):
        raise ValidationError('Tasdiqlash muddati tugagan yoki ma’lumot o‘zgargan. Qayta hisoblang.')
    if (payload.get('user') != user.pk or payload.get('lot') != str(lot.pk)
            or payload.get('form') != normalized_fields(data)):
        raise ValidationError('Maydonlar o‘zgargan. Yangilangan summani qayta hisoblang.')
    return payload['snapshot']
