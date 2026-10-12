#!/usr/bin/env python3
"""Standalone on-site HTTPS shipper with durable SQLite queue (Python stdlib only).

This is NOT a Modbus driver. Your site-specific poller reads sensors and passes
measurements in the documented JSON format to 'enqueue'. Run 'flush' on a timer.

Environment:
 IOT_URL=https://<host>/app/api/iot/v1/readings/
 IOT_BEARER=<gateway-uuid>.<one-time-secret>
 IOT_QUEUE_DB=/var/lib/iot/queue.db
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def db():
    path=os.environ.get('IOT_QUEUE_DB','iot_queue.sqlite3')
    root=os.path.dirname(os.path.abspath(path))
    os.makedirs(root,exist_ok=True)
    connection=sqlite3.connect(path,timeout=30)
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('''CREATE TABLE IF NOT EXISTS event_queue (
        event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
        created_at TEXT NOT NULL, sent_at TEXT
    )''')
    return connection


def enqueue(filename):
    with open(filename,'r',encoding='utf-8') as handle:
        rows=json.load(handle)
    if not isinstance(rows,list) or not rows:
        raise ValueError('JSON faylda bir yoki bir nechta o‘lchovdan iborat ro‘yxat bo‘lsin.')
    made=0
    with db() as con:
        for raw in rows:
            if not isinstance(raw,dict):
                raise ValueError('Noto‘g‘ri datchik qaydi.')
            obj={key:raw[key] for key in ('device_code','measured_at','temperature','humidity')}
            if not isinstance(obj['device_code'],str) or not isinstance(obj['measured_at'],str):
                raise ValueError('device_code va measured_at satr bo‘lishi kerak.')
            # Stable ID across offline retries. Same sensor/time must not differ
            # on resend. If a vendor has its own unique sequence, use it.
            event_id=raw.get('event_id') or hashlib.sha256(
                (obj['device_code']+'|'+obj['measured_at']).encode('utf-8')
            ).hexdigest()[:48]
            if not isinstance(event_id,str) or not 1<=len(event_id)<=80:
                raise ValueError('event_id noto‘g‘ri.')
            obj['event_id']=event_id
            cur=con.execute('INSERT OR IGNORE INTO event_queue VALUES (?, ?, ?, NULL)',
                (event_id,json.dumps(obj,ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat()))
            made+=cur.rowcount
    print(f'Navbatga qo‘shildi: {made}; dublikat e’tiborsiz qoldirildi: {len(rows)-made}')


def flush():
    url=os.environ.get('IOT_URL','').strip()
    token=os.environ.get('IOT_BEARER','').strip()
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or not url.endswith('/'):
        raise ValueError('IOT_URL haqiqiy HTTPS endpoint bo‘lishi shart.')
    if len(token)<40 or '.' not in token:
        raise ValueError('IOT_BEARER sozlanmagan.')
    with db() as con:
        batch=con.execute('SELECT event_id,payload FROM event_queue WHERE sent_at IS NULL ORDER BY created_at,event_id LIMIT 50').fetchall()
        if not batch:
            print('Navbat bo‘sh.')
            return
        payload={'readings':[json.loads(row[1]) for row in batch]}
        request=urllib.request.Request(url,
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type':'application/json','Authorization':f'Bearer {token}'},
            method='POST')
        try:
            with urllib.request.urlopen(request,timeout=20) as resp:
                result=json.loads(resp.read(1024).decode('utf-8'))
                if resp.status!=200 or result.get('ok') is not True:
                    raise RuntimeError('Server yuborishni tasdiqlamadi')
                if result.get('inserted',0)+result.get('duplicates',0)!=len(batch):
                    raise RuntimeError('Server faqat qisman tasdiqladi')
        except (urllib.error.URLError,TimeoutError,RuntimeError,ValueError) as exc:
            # Do not print Bearer token or request URL (or Telegram secrets).
            print('Ulanish/tasdiq xatosi; navbat saqlandi:', type(exc).__name__,file=sys.stderr)
            sys.exit(2)
        con.executemany('UPDATE event_queue SET sent_at=? WHERE event_id=?',
            [(datetime.now(timezone.utc).isoformat(),event_id) for event_id,_ in batch])
        print('ERP tasdiqladi:',len(batch),'o‘lchov. Qolgan navbat keyingi flushda yuboriladi.')


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='action',required=True)
    cmd=sub.add_parser('enqueue',help='Mahalliy Modbus/Wi-Fi adapteri yaratgan JSON faylni navbatga qo‘shish')
    cmd.add_argument('file')
    sub.add_parser('flush',help='Navbatdagi o‘lchovlarni HTTPS orqali bulutga yuborish')
    args=parser.parse_args()
    if args.action=='enqueue':
        enqueue(args.file)
    else:
        flush()


if __name__=='__main__':
    main()
