"""One-shot staging Telegram Bot API verification without exposing the token."""
import json
import os
import urllib.error
import urllib.request
from django.core.management.base import BaseCommand,CommandError

EXPECTED_USERNAME='MuzlatkichtestBot'
STAGING_ENV='79dae0a2-be02-4dc2-ac16-3675ffc1aa62'


def verify_bot():
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token or ':' not in token or not token.split(':',1)[0].isdigit():
        raise CommandError('Telegram bot tokeni kiritilmagan yoki shakli noto‘g‘ri.')
    endpoint='https://api.telegram.org/bot'+token+'/getMe'
    try:
        # Do not include the endpoint or server response body in exceptions!
        req=urllib.request.Request(endpoint,headers={'Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=8) as resp:
            data=json.loads(resp.read(4096).decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise CommandError(f'Telegram API HTTP {e.code}; tokenni BotFather orqali tekshiring.') from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise CommandError('Telegram API ulanish xatosi yoki vaqt chegarasi.') from None
    except (ValueError,UnicodeDecodeError):
        raise CommandError('Telegram API javobi noto‘g‘ri formatda.') from None
    result=data.get('result') or {}
    if data.get('ok') is not True or result.get('username','').lower()!=EXPECTED_USERNAME.lower():
        raise CommandError('Bot identifikatori kutilgan sinov botiga mos emas.')
    return result.get('username')


class Command(BaseCommand):
    help='STAGING bot tokenini Telegram getMe bilan tekshiradi. Tokenni chiqarmaydi.'
    def handle(self,*args,**options):
        if (os.environ.get('RAILWAY_ENVIRONMENT_ID')!=STAGING_ENV or
            os.environ.get('ALLOW_STAGING_DEMO_SEED')!='1'):
            raise CommandError('Bu tekshiruv faqat maxsus staging xizmatidan bajariladi.')
        username=verify_bot()
        self.stdout.write(f'TELEGRAM GETME OK: @{username} (token yashirilgan, xabar hali yuborilmagan)')
