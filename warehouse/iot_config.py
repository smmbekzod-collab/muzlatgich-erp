"""Export local-edge device configuration WITHOUT secret tokens or vendor guesses.

Authentication is Django session + organization admin permissions, never the
gateway API token. No production data/credentials are embedded in the file.
"""
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from core import access
from .iot_models import IoTDevice, IoTGateway
from .iot_views import admin_orgs


def edge_template(gateway, devices):
    """Build a non-runnable template. All vendor-specific fields stay blank."""
    devices_json=[]
    for d in devices:
        row={'code':d.code,'transport':d.transport,
             '_camera_number':d.camera.number,
             '_camera_name':d.camera.name or f'{d.camera.number}-kamera',
             '_sensor_model':d.model_name or 'MODEL ANIQLANMAGAN'}
        if d.transport=='modbus_rtu':
            row.update({
                'address':d.address,
                'temperature_function':'input',
                'temperature_register':None,
                'temperature_signed':False,
                'temperature_scale':None,
                'humidity_function':'input',
                'humidity_register':None,
                'humidity_scale':None,
            })
        elif d.transport=='http_json':
            row.update({
                'url':'',
                'temperature_path':'',
                'humidity_path':'',
                'timestamp_path':'',
                'bearer_token_env':'',
            })
        elif d.transport=='mqtt':
            row.update({
                'topic':'',
                'temperature_path':'',
                'humidity_path':'',
                'timestamp_path':'',
            })
        else:
            row['_adapter_status']='Adapter hali qo‘shilmagan'
        devices_json.append(row)
    return {
        '_notice':'TEXNIK SHABLON. Harorat/namlik registrlari, JSON path, MQTT topic va sertifikatni ishlab chiqaruvchi pasporti asosida to‘ldirmasdan ishga tushirmang.',
        '_organization':gateway.organization.name,
        '_facility':gateway.facility.name,
        '_gateway_name':gateway.name,
        '_gateway_id':str(gateway.pk),
        '_generated_at':timezone.now().isoformat(),
        '_contains_secrets':False,
        'serial':{
            'port':'',
            'baudrate':9600,
            'parity':'N',
            'stopbits':1,
            'bytesize':8,
            'timeout':2,
            '_notice':'Ulanish tezligi/parity/port datchik pasportidan aniqlansin',
        },
        'mqtt':{
            'host':'',
            'port':8883,
            'tls':True,
            'ca_file':'',
            'username_env':'IOT_MQTT_USER',
            'password_env':'IOT_MQTT_PASSWORD',
        },
        'devices':devices_json,
    }


@never_cache
@login_required
@require_GET
def export_edge_config(request,gateway_id):
    """Only organization's administrator/superuser, scoped to actual facility."""
    allowed=admin_orgs(request.user).filter(is_active=True)
    facilities=access.facilities(request.user).filter(organization__in=allowed,is_active=True)
    gateway=get_object_or_404(IoTGateway.objects.select_related('organization','facility'),
        pk=gateway_id, organization__in=allowed, facility__in=facilities)
    permitted_cameras=access.cameras(request.user).filter(
        organization=gateway.organization,facility=gateway.facility)
    devices=list(IoTDevice.objects.filter(
        gateway=gateway,camera__in=permitted_cameras).select_related('camera')
        .order_by('camera__number','code'))
    response=JsonResponse(edge_template(gateway,devices),
        json_dumps_params={'ensure_ascii':False,'indent':2})
    response['Content-Disposition']=f'attachment; filename="iot-edge-{gateway.pk}.json"'
    response['Cache-Control']='no-store, private'
    response['Referrer-Policy']='no-referrer'
    response['X-Content-Type-Options']='nosniff'
    return response
