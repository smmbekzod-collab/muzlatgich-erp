#!/usr/bin/env python3
"""On-site Universal IoT adapter: Wi-Fi HTTP, RS485 Modbus RTU and MQTT.

Never install this as a polling process on Railway: it runs on a LOCAL edge PC
or gateway, outside the cold rooms. It only reads devices and enqueues values;
scripts/iot_gateway_shipper.py later forwards the durable queue over HTTPS.

Device-specific register mappings and JSON keys must come from vendor manuals.
No universal auto-detection or cloud-broker bridge is implied.
"""
import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.iot_gateway_shipper import enqueue_rows

MAX_DEVICES=128
ID_RE=re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def configuration(path):
    cfg=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(cfg,dict) or not isinstance(cfg.get('devices'),list):
        raise ValueError('Konfiguratsiyada devices ro‘yxati bo‘lishi kerak')
    devices=cfg['devices']
    if not 1 <= len(devices) <= MAX_DEVICES:
        raise ValueError('1–128 ta qurilma bo‘lishi mumkin')
    codes=[]
    for dev in devices:
        if not isinstance(dev,dict) or not ID_RE.fullmatch(str(dev.get('code',''))):
            raise ValueError('device.code faqat harf, raqam, _ va -')
        if dev.get('transport') not in ('http_json','modbus_rtu','mqtt'):
            raise ValueError('Hozir qo‘llab-quvvatlanadigan transport: http_json, modbus_rtu, mqtt')
        codes.append(dev['code'])
        if dev['transport']=='mqtt':
            topic=dev.get('topic')
            if not isinstance(topic,str) or not topic or any(x in topic for x in ('#','+','\x00')):
                raise ValueError('MQTT har datchik uchun aniq topic bo‘lishi kerak')
    if len(set(codes))!=len(codes):
        raise ValueError('Qurilma kodlari yagona bo‘lishi kerak')
    topics=[d['topic'] for d in devices if d['transport']=='mqtt']
    if len(set(topics))!=len(topics):
        raise ValueError('MQTT topiclar takrorlanmasligi kerak')
    return cfg


def get_path(payload,path):
    if not isinstance(path,str) or not path or len(path)>120:
        raise ValueError('Sensor JSON field path belgilanmagan')
    val=payload
    for key in path.split('.'):
        if not isinstance(val,dict) or key not in val:
            raise ValueError('Ishlab chiqaruvchi JSON manzilida kalit topilmadi: '+path)
        val=val[key]
    return val


def decimal_value(value,scale,low,high,label):
    if isinstance(value,bool) or value is None:
        raise ValueError(label+' son bo‘lishi shart')
    try:
        v=Decimal(str(value))*Decimal(str(scale))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(label+' noto‘g‘ri')
    if not v.is_finite() or not low<=v<=high:
        raise ValueError(label+' me’yordan tashqarida')
    return str(v.quantize(Decimal('0.01')))


def iso_timestamp(value=None):
    if value is None:
        dt=datetime.now(timezone.utc)
    elif isinstance(value,str) and len(value)<=45:
        try:
            dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:
            raise ValueError('O‘lchov vaqti ISO-8601 emas')
        if dt.tzinfo is None:
            raise ValueError('Vaqt zonasi ko‘rsatilmagan')
    else:
        raise ValueError('O‘lchov vaqti noto‘g‘ri')
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


def normalize(dev,payload,*,require_timestamp=False):
    """Vendor fields -> platform protocol, with validated units and UTC time."""
    if not isinstance(payload,dict):
        raise ValueError('Sensor JSON obyekt bo‘lishi shart')
    temperature=get_path(payload,dev.get('temperature_path','temperature'))
    humidity=get_path(payload,dev.get('humidity_path','humidity'))
    path=dev.get('timestamp_path')
    if require_timestamp and not path:
        raise ValueError('MQTT o‘lchovlarida timestamp_path majburiy')
    measured=iso_timestamp(get_path(payload,path) if path else None)
    # event_id is stable for vendor timestamp; ephemeral HTTP polling may use
    # current poll time. Cloud idempotency also includes device_code.
    return {
        'device_code':dev['code'],
        'measured_at':measured,
        'temperature':decimal_value(temperature,dev.get('temperature_scale','1'),Decimal('-80'),Decimal('80'),'Harorat'),
        'humidity':decimal_value(humidity,dev.get('humidity_scale','1'),Decimal('0'),Decimal('100'),'Namlik'),
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Datchik URL qayta yo‘naltirildi; redirect taqiqlangan')


def check_http_url(raw):
    if not isinstance(raw,str) or len(raw)>300:
        raise ValueError('URL noto‘g‘ri')
    url=urllib.parse.urlsplit(raw)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('Faqat HTTP(S) GET URL')
    if url.scheme=='http':
        # Plain HTTP only on literal private/link-local loopback IPv4/IPv6.
        # Public hostname on HTTP could leak a device auth header.
        try:
            addr=ipaddress.ip_address(url.hostname)
        except ValueError:
            raise ValueError('Oddiy HTTP uchun faqat lokal IP manzil; HTTPS yoki IP ishlating')
        if not (addr.is_private or addr.is_link_local or addr.is_loopback):
            raise ValueError('Tashqi HTTP manzilga ruxsat yo‘q')
    return raw


def collect_http(dev,opener=None):
    url=check_http_url(dev.get('url'))
    if opener is None:
        opener=urllib.request.build_opener(NoRedirect())
    headers={'Accept':'application/json'}
    token_env=dev.get('bearer_token_env')
    if token_env:
        if not isinstance(token_env,str) or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',token_env):
            raise ValueError('bearer_token_env noto‘g‘ri')
        token=os.environ.get(token_env)
        if not token:
            raise ValueError('Sensor autentifikatsiya kaliti muhitda yo‘q')
        headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,headers=headers,method='GET')
    with opener.open(req,timeout=6) as resp:
        if getattr(resp,'status',200)!=200:
            raise ValueError('Sensor HTTP 200 javob bermadi')
        raw=resp.read(8193)
    if len(raw)>8192:
        raise ValueError('Sensor JSON hajmi 8KB dan katta')
    return normalize(dev,json.loads(raw.decode('utf-8')))


def signed16(word):
    if not isinstance(word,int) or not 0<=word<=65535:
        raise ValueError('Modbus registr qiymati noto‘g‘ri')
    return word if word < 32768 else word - 65536


def _modbus_register(client,dev,kind):
    function=dev.get(kind+'_function','input')
    if function not in ('input','holding'):
        raise ValueError('Modbus funksiya input yoki holding bo‘lsin')
    reg=dev.get(kind+'_register')
    if not isinstance(reg,int) or not 0<=reg<=65535:
        raise ValueError(kind+'_register 0-based manzil bo‘lishi kerak')
    slave=dev.get('address')
    if not isinstance(slave,int) or not 1<=slave<=247:
        raise ValueError('Modbus slave manzili 1–247 bo‘lsin')
    reader=client.read_input_registers if function=='input' else client.read_holding_registers
    result=reader(address=reg,count=1,device_id=slave)
    if result is None or result.isError() or not getattr(result,'registers',None):
        raise ValueError('Modbus o‘lchovga javob qaytmadi')
    word=result.registers[0]
    return signed16(word) if dev.get(kind+'_signed',False) else word


def collect_modbus(dev,client):
    temp=_modbus_register(client,dev,'temperature')
    hum=_modbus_register(client,dev,'humidity')
    # Convert vendor integer and scaling via the same validation path.
    return normalize(dev,{'temperature':temp,'humidity':hum})


def _serial_factory(serial):
    try:
        from pymodbus.client import ModbusSerialClient
    except ImportError as e:
        raise RuntimeError('RS485 uchun pip install -r requirements-iot-edge.txt') from e
    port=serial.get('port')
    if not isinstance(port,str) or not port:
        raise ValueError('RS485 serial.port majburiy')
    return ModbusSerialClient(
        port=port,
        baudrate=int(serial.get('baudrate',9600)),
        parity=serial.get('parity','N'),
        stopbits=int(serial.get('stopbits',1)),
        bytesize=int(serial.get('bytesize',8)),
        timeout=float(serial.get('timeout',2))
    )


def poll(config,*,http_opener=None,serial_factory=None):
    """Poll each source; queue healthy readings even if one sensor fails."""
    readings=[]
    for dev in config['devices']:
        if dev['transport']!='http_json':
            continue
        try:
            readings.append(collect_http(dev,http_opener))
        except Exception as exc:
            print(f'Wi-Fi datchik {dev["code"]}: {type(exc).__name__}',file=sys.stderr)
    modbus=[d for d in config['devices'] if d['transport']=='modbus_rtu']
    if modbus:
        factory=serial_factory or _serial_factory
        client=None
        try:
            client=factory(config.get('serial',{}))
            if not client.connect():
                raise RuntimeError('RS485 serial portga ulanib bo‘lmadi')
            for dev in modbus:
                try:
                    readings.append(collect_modbus(dev,client))
                except Exception as exc:
                    print(f'RS485 datchik {dev["code"]}: {type(exc).__name__}',file=sys.stderr)
        except Exception as exc:
            print('RS485 gateway: '+type(exc).__name__,file=sys.stderr)
        finally:
            if client:
                client.close()
    if readings:
        enqueue_rows(readings)
    return len(readings)


def handle_mqtt(topic,raw,config,retained=False):
    """Broker callback -> local durable queue. Require vendor measurement time."""
    devices={d['topic']:d for d in config['devices'] if d['transport']=='mqtt'}
    dev=devices.get(topic)
    if not dev or retained:
        return False
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>8192:
        raise ValueError('MQTT JSON xabari 8KB dan oshmasligi kerak')
    item=normalize(dev,json.loads(raw.decode('utf-8')),require_timestamp=True)
    enqueue_rows([item])
    return True


def listen_mqtt(config):
    items=[d for d in config['devices'] if d['transport']=='mqtt']
    if not items:
        raise ValueError('MQTT qurilmalar konfiguratsiyada mavjud emas')
    broker=config.get('mqtt',{})
    if not broker.get('tls',False):
        raise ValueError('MQTT broker uchun sertifikatli TLS talab qilinadi')
    host=broker.get('host')
    if not isinstance(host,str) or not host:
        raise ValueError('MQTT broker host belgilanmagan')
    try:
        import paho.mqtt.client as mqtt
    except ImportError as e:
        raise RuntimeError('MQTT uchun pip install -r requirements-iot-edge.txt') from e
    client=mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.tls_set(ca_certs=broker.get('ca_file') or None)
    username=os.environ.get(broker.get('username_env','IOT_MQTT_USER'),'')
    password=os.environ.get(broker.get('password_env','IOT_MQTT_PASSWORD'),'')
    if username:
        client.username_pw_set(username,password)
    def on_connect(_client,_userdata,_flags,reason_code,_properties):
        if reason_code != 0:
            print('MQTT broker autentifikatsiyasi rad etildi',file=sys.stderr)
            return
        for item in items:
            _client.subscribe(item['topic'],qos=1)
    def on_message(_client,_userdata,msg):
        try:
            handle_mqtt(msg.topic,msg.payload,config,retained=msg.retain)
        except Exception as exc:
            print(f'MQTT sensor xabari rad etildi: {type(exc).__name__}',file=sys.stderr)
    client.on_connect=on_connect
    client.on_message=on_message
    client.connect(host,int(broker.get('port',8883)),keepalive=60)
    print('MQTT tinglash boshlandi (TLS). HTTPS jo‘natishni alohida timer bajarsin.')
    client.loop_forever(retry_first_connection=True)


def main():
    parser=argparse.ArgumentParser(description='On-site IoT adapter; never run on Railway')
    parser.add_argument('--config',required=True)
    parser.add_argument('command',choices=['poll','mqtt'])
    args=parser.parse_args()
    cfg=configuration(args.config)
    if args.command=='poll':
        n=poll(cfg)
        print(f'Navbatga kiritilgan o‘lchovlar: {n}')
        if n==0:
            raise SystemExit(2)
    else:
        listen_mqtt(cfg)


if __name__=='__main__':
    main()
