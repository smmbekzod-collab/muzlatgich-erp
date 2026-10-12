"""Offline edge-adapter acceptance tests: fake devices, no network or Telegram."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import iot_gateway_shipper as shipper
from scripts import iot_edge_bridge as edge


NOW='2026-10-12T15:33:00+05:00'


class MockResponse:
    status=200
    def __init__(self, payload):
        self.payload=json.dumps(payload).encode('utf-8')
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,maxlen):
        return self.payload[:maxlen]


class FakeHTTP:
    def __init__(self,payload):
        self.payload=payload
        self.requests=[]
    def open(self,request,timeout=6):
        self.requests.append((request.full_url,request.get_method()))
        return MockResponse(self.payload)


class FakeModbusResult:
    def __init__(self,value,error=False):
        self.registers=[value]
        self.error=error
    def isError(self):
        return self.error


class FakeSerial:
    def __init__(self):
        self.addresses=[]
        self.closed=False
    def connect(self):
        return True
    def read_input_registers(self,*,address,count,device_id):
        self.addresses.append(device_id)
        if address==0:
            return FakeModbusResult(0xFFF6) # −10 -> −1.0°C
        if address==1:
            return FakeModbusResult(850)   # 85.0% RH
        return FakeModbusResult(0,True)
    def close(self):
        self.closed=True


class IoTEdgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'IOT_QUEUE_DB':str(Path(self.temp.name)/'queue.sqlite3')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def queued(self):
        with shipper.db() as con:
            return con.execute('SELECT payload FROM event_queue ORDER BY event_id').fetchall()

    def test_queue_multiple_cameras_same_event_id(self):
        rows=[
            {'device_code':f'cam{i:02d}','event_id':'common-vendor-serial-6',
             'measured_at':NOW,'temperature':'1.2','humidity':'86'}
            for i in range(1,26)]
        self.assertEqual(shipper.enqueue_rows(rows),25)
        self.assertEqual(shipper.enqueue_rows(rows),0)
        self.assertEqual(len(self.queued()),25)
        self.assertEqual({json.loads(row[0])['device_code'] for row in self.queued()},
                         {f'cam{i:02d}' for i in range(1,26)})

    def test_http_json_nested_and_auth_env(self):
        dev={
            'code':'cam02','transport':'http_json',
            'url':'http://192.168.1.80/api/status',
            'temperature_path':'data.temp_c',
            'humidity_path':'data.rh',
            'timestamp_path':'data.timestamp',
            'bearer_token_env':'IOT_TEST_SENSOR'
        }
        client=FakeHTTP({'data':{'temp_c':1.7,'rh':87.3,'timestamp':NOW}})
        with patch.dict(os.environ,{'IOT_TEST_SENSOR':'dummy-not-live'}):
            out=edge.collect_http(dev,client)
        self.assertEqual(client.requests,[('http://192.168.1.80/api/status','GET')])
        self.assertEqual(out['temperature'],'1.70')
        self.assertEqual(out['humidity'],'87.30')
        self.assertEqual(out['device_code'],'cam02')
        self.assertTrue(out['measured_at'].endswith('+00:00'))

    def test_http_public_plaintext_and_redirect_blocked(self):
        for raw in ['http://example.com/api','http://8.8.8.8/',
                    'file:///etc/passwd','http://user:pass@192.168.1.1/data']:
            with self.assertRaises(ValueError):
                edge.check_http_url(raw)
        self.assertEqual(edge.check_http_url('https://example.com/api'),
                         'https://example.com/api')
        with self.assertRaises(ValueError):
            edge.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_modbus_25_device_mapping(self):
        fake=FakeSerial()
        devices=[
            {'code':f'cam{i:02d}','transport':'modbus_rtu','address':i,
             'temperature_register':0,'temperature_scale':'0.1',
             'temperature_signed':True,'humidity_register':1,
             'humidity_scale':'0.1'}
            for i in range(1,26)]
        n=edge.poll({'devices':devices,'serial':{'port':'/dev/ttyUSB0'}},
                    serial_factory=lambda _:fake)
        self.assertEqual(n,25)
        self.assertTrue(fake.closed)
        self.assertEqual(len(self.queued()),25)
        vals=[json.loads(row[0]) for row in self.queued()]
        self.assertTrue(all(x['temperature']=='-1.00' for x in vals))
        self.assertTrue(all(x['humidity']=='85.00' for x in vals))
        self.assertEqual(len(set(fake.addresses)),25)

    def test_mqtt_topic_timestamp_and_retained(self):
        cfg={'devices':[{'code':'cam03','transport':'mqtt','topic':'site-a/cam03',
            'timestamp_path':'measured_at'}]}
        sample=json.dumps({'temperature':1.2,'humidity':88,'measured_at':NOW}).encode()
        self.assertFalse(edge.handle_mqtt('site-a/unknown',sample,cfg))
        self.assertFalse(edge.handle_mqtt('site-a/cam03',sample,cfg,retained=True))
        self.assertEqual(len(self.queued()),0)
        self.assertTrue(edge.handle_mqtt('site-a/cam03',sample,cfg))
        self.assertTrue(edge.handle_mqtt('site-a/cam03',sample,cfg))
        self.assertEqual(len(self.queued()),1)
        with self.assertRaises(ValueError):
            edge.handle_mqtt('site-a/cam03',b'{"temperature":1,"humidity":90}',cfg)

    def test_bad_payload_and_invalid_number(self):
        dev={'code':'cam01','transport':'http_json'}
        for sample in [
            {'temperature':None,'humidity':60},
            {'temperature':'nan','humidity':60},
            {'temperature':1,'humidity':105},
            {'temperature':1,'humidity':60,'ts':'2026-10-12 10:00:00'}
        ][:3]:
            with self.assertRaises(ValueError):
                edge.normalize(dev,sample)

    def test_validate_gateway_config(self):
        config={'devices':[{'code':'cam01','transport':'mqtt','topic':'a/1'},
                           {'code':'cam02','transport':'mqtt','topic':'a/2'}]}
        path=Path(self.temp.name)/'edge.json'
        path.write_text(json.dumps(config))
        self.assertEqual(len(edge.configuration(str(path))['devices']),2)
        config['devices'][1]['topic']='a/1'
        path.write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            edge.configuration(str(path))
        config['devices'][1]['topic']='a/+'
        path.write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            edge.configuration(str(path))

    def test_validate_rejects_unfinished_exported_sensor_mapping(self):
        base={'serial':{'port':'/dev/ttyUSB0'},'devices':[{
            'code':'cam01','transport':'modbus_rtu','address':1,
            'temperature_function':'input','temperature_register':None,
            'temperature_scale':None,'humidity_function':'input',
            'humidity_register':None,'humidity_scale':None
        }]}
        with self.assertRaises(ValueError):
            edge.validate_config(base,'all')
        row=base['devices'][0]
        row.update(temperature_register=0,temperature_scale='0.1',
                   humidity_register=1,humidity_scale='0.1')
        self.assertEqual(edge.validate_config(base,'all'),1)
        base['devices'].append({'code':'cam02','transport':'http_json',
            'url':'','temperature_path':'','humidity_path':''})
        with self.assertRaises(ValueError):
            edge.validate_config(base,'all')
        base['devices'][1].update(url='http://192.168.1.80/status',
                                   temperature_path='temperature',
                                   humidity_path='humidity')
        self.assertEqual(edge.validate_config(base,'all'),2)

    def test_validate_mqtt_requires_tls_and_vendor_timestamp(self):
        config={'mqtt':{'host':'192.168.1.20','tls':True},
                'devices':[{'code':'cam03','transport':'mqtt',
                    'topic':'sensors/cam03','temperature_path':'temp',
                    'humidity_path':'humidity','timestamp_path':'measured_at'}]}
        self.assertEqual(edge.validate_config(config,'mqtt'),1)
        config['mqtt']['tls']=False
        with self.assertRaises(ValueError):
            edge.validate_config(config,'mqtt')
        config['mqtt']['tls']=True
        config['devices'][0]['timestamp_path']=''
        with self.assertRaises(ValueError):
            edge.validate_config(config,'mqtt')

    def test_http_failure_does_not_block_healthy_camera(self):
        client=FakeHTTP({'temperature':2.3,'humidity':83})
        cfg={'devices':[
            {'code':'cam01','transport':'http_json','url':'file:///etc/passwd'},
            {'code':'cam02','transport':'http_json','url':'http://192.168.1.12/status'}
        ]}
        self.assertEqual(edge.poll(cfg,http_opener=client),1)
        self.assertEqual(len(self.queued()),1)


if __name__=='__main__':
    unittest.main()
