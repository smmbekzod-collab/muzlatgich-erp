"""One-off staging group discovery. Does not send messages or reveal token.

Telegram private invite links are *not* chat IDs. getUpdates surfaces the
numeric ID only after Telegram delivers a group event to the bot.
"""
import json
import os
import urllib.error
import urllib.request
from django.core.management.base import BaseCommand,CommandError

STAGING_ID='79dae0a2-be02-4dc2-ac16-3675ffc1aa62'
EXPECTED_BOT='MuzlatkichtestBot'
INVITE='https://t.me/+1ErA_d0ypXRiZWZi'


def api(method,params=None):
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token or ':' not in token:
        raise CommandError('Telegram tokeni sozlanmagan')
    url='https://api.telegram.org/bot'+token+'/'+method
    try:
        payload=json.dumps(params or {}).encode('utf-8')
        req=urllib.request.Request(url,data=payload,
            headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=12) as resp:
            data=json.loads(resp.read(80000).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise CommandError(f'Telegram HTTP {exc.code} ({method})') from None
    except (urllib.error.URLError,TimeoutError,OSError,ValueError,UnicodeDecodeError):
        raise CommandError(f'Telegram {method} ulanish yoki javob xatosi') from None
    if not data.get('ok'):
        raise CommandError(f'Telegram {method} muvaffaqiyatsiz')
    return data.get('result')


class Command(BaseCommand):
    help='Show only Telegram group chat metadata from bot updates; no token or message content.'
    def handle(self,*args,**options):
        if os.environ.get('RAILWAY_ENVIRONMENT_ID')!=STAGING_ID or os.environ.get('ALLOW_STAGING_DEMO_SEED')!='1':
            raise CommandError('Faqat tasdiqlangan STAGING xizmatidan bajariladi')
        me=api('getMe')
        if me.get('username','').lower()!=EXPECTED_BOT.lower():
            raise CommandError('Boshqa bot. Jarayon to‘xtatildi.')
        info=api('getWebhookInfo')
        if info.get('url'):
            raise CommandError('Telegram webhook faol: getUpdates ishlamaydi. Webhook sozlamalarini tekshiring.')
        updates=api('getUpdates',{'limit':100,'timeout':0})
        groups={}
        for u in updates:
            for field in ('message','edited_message','my_chat_member','chat_member','channel_post','edited_channel_post'):
                entry=u.get(field) or {}
                chat=entry.get('chat') or {}
                if chat.get('type') in ('group','supergroup'):
                    groups[int(chat['id'])]=chat.get('title','(nomsiz guruh)')
        self.stdout.write(f'TELEGRAM DISCOVERY: bot=@{EXPECTED_BOT} updates={len(updates)} unique_groups={len(groups)}')
        for chat_id,title in sorted(groups.items()):
            try:
                details=api('getChat',{'chat_id':chat_id})
                membership=api('getChatMember',{'chat_id':chat_id,'user_id':me['id']})
                status=membership.get('status','unknown')
                match=(details.get('invite_link','').rstrip('/')==INVITE)
                # Telegram getChat may expose another invite; mismatch is not definite.
                self.stdout.write('GROUP '+json.dumps({
                   'chat_id':chat_id,'title':title[:100],
                   'bot_status':status,'invite_link_exact_match':match,
                   'bot_admin':status in ('administrator','creator'),
                },ensure_ascii=False))
            except CommandError:
                self.stdout.write(f'GROUP chat_id={chat_id} chat_metadata_unavailable')
        if not groups:
            self.stdout.write('GROUP_NOT_FOUND: guruhga /chatid yoki /start@MuzlatkichtestBot yuboring, so‘ng qayta tekshiring.')
