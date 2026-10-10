import calendar
from datetime import date,timedelta
from decimal import Decimal,ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError,PermissionDenied
from django.utils import timezone
from core.access import authorize,cameras
from core.models import Camera
from .models import Lot,Operation,Tariff,Customer

ZERO=Decimal('0')
TIER_FIELDS=('tier_1_10','tier_11_15','tier_16_25','tier_26_30','tier_31_plus')

def tiered_rate(lot, days):
    """Full one-time per-kg price based on total age, not an accumulating daily fee."""
    age = max(1,days)
    field = ('tier_1_10' if age<=10 else 'tier_11_15' if age<=15 else
             'tier_16_25' if age<=25 else 'tier_26_30' if age<=30 else 'tier_31_plus')
    rate=getattr(lot,field)
    if rate is None:
        raise ValidationError('Muddatga ko‘ra tarifning barcha bosqichlari belgilanishi kerak.')
    return rate

def tiered_days(start, on):
    return max(1,(on-start).days+1)

def money(value):return Decimal(value).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
def date_check(day,start):
    if day<start:raise ValidationError('Sana oldingi harakat yoki kirim sanasidan oldin bo‘lishi mumkin emas.')
    if day>timezone.localdate():raise ValidationError('Kelajak sanasiga hujjat yozib bo‘lmaydi.')
def weights(boxes,gross,tare):
    if boxes<=0 or gross<=0 or tare<0 or tare>=gross:raise ValidationError('Yashik va brutto musbat, tara esa 0 dan brutto vazngacha bo‘lishi kerak.')
def month_boundary(start,index):
    month=start.month-1+index
    y=start.year+month//12;m=month%12+1
    return date(y,m,min(start.day,calendar.monthrange(y,m)[1]))
def storage_total(lot,through):
    if through<lot.received_on:return ZERO
    result=ZERO;i=0
    while True:
        start=month_boundary(lot.received_on,i)
        if start>through:break
        end=month_boundary(lot.received_on,i+1)
        days=(min(through+timedelta(days=1),end)-start).days
        result+=lot.rate if lot.storage_mode=='full' else lot.rate*Decimal(days)/Decimal((end-start).days)
        i+=1
    return money(result)
def totals(lot):
    sums=lot.operations.aggregate(charged=Sum('charge'),paid=Sum('payment'))
    charged=sums['charged'] or ZERO;paid=sums['paid'] or ZERO
    return {'charged':charged,'paid':paid,'debt':max(ZERO,charged-paid),'advance':max(ZERO,paid-charged)}
def dispatch_snapshot(lot):
    """Signed preview inputs that must still hold while the lot is locked."""
    balance = totals(lot)
    return {
        'camera':lot.camera_id, 'boxes':lot.boxes,
        'gross':str(lot.gross), 'tare':str(lot.tare),
        'storage_billed':str(lot.storage_billed),
        'closed_on':lot.closed_on.isoformat() if lot.closed_on else None,
        'last_stock_date':lot.last_stock_date.isoformat(),
        'charged':str(balance['charged']), 'paid':str(balance['paid']),
    }

def pending(lot,as_of=None):
    as_of=as_of or timezone.localdate()
    if lot.closed_on or as_of<lot.received_on:return ZERO
    if lot.service=='storage':return max(ZERO,storage_total(lot,as_of)-lot.storage_billed)
    if lot.service=='tiered':
        kg=lot.gross if lot.basis=='gross' else lot.net
        return money(kg*tiered_rate(lot,tiered_days(lot.received_on,as_of)))
    kg=lot.gross if lot.basis=='gross' else lot.net
    return money(kg*lot.rate*((as_of-lot.received_on).days+1))
def quote(lot,kind,day,boxes=0,gross=ZERO,tare=ZERO):
    date_check(day,lot.last_stock_date)
    if lot.closed_on:raise ValidationError('Partiya yopilgan.')
    if kind in ['dispatch','loss']:
        if kind=='loss' and boxes==0:
            if gross<=0 or tare<0 or tare>=gross:raise ValidationError('Yo‘qotish vazni noto‘g‘ri.')
        else:weights(boxes,gross,tare)
        if boxes>lot.boxes or gross>lot.gross or tare>lot.tare or gross-tare>lot.net:
            raise ValidationError('Chiqariladigan miqdor yoki vazn qoldiqdan ortiq.')
        if boxes==lot.boxes and (gross!=lot.gross or tare!=lot.tare):
            raise ValidationError('Oxirgi yashiklar uchun butun qoldiq brutto va tarani kiriting. Tafovutni avval yo‘qotish sifatida qayd eting.')
        if boxes<lot.boxes and (gross>=lot.gross or gross-tare>=lot.net):
            raise ValidationError('Qoladigan yashiklar uchun musbat mahsulot vazni qolishi kerak.')
    days=max(0,(day-lot.received_on).days+(1 if lot.bill_exit_day else 0))
    if lot.service=='tiered':
        if kind=='storage_bill':raise ValidationError('Bu partiya oylik saqlama xizmatida emas.')
        days=tiered_days(lot.received_on,day)
        charge=money((gross if lot.basis=='gross' else gross-tare)*tiered_rate(lot,days))
        target=lot.storage_billed
    elif lot.service=='cooling':
        if kind=='storage_bill':raise ValidationError('Bu partiya saqlama xizmatida emas.')
        charge=money((gross if lot.basis=='gross' else gross-tare)*lot.rate*days)
        target=lot.storage_billed
    else:
        through=day if kind=='storage_bill' or lot.bill_exit_day else day-timedelta(days=1)
        if lot.storage_mode=='full':through=max(lot.received_on,through)
        target=storage_total(lot,through)
        charge=max(ZERO,target-lot.storage_billed)
    financial=totals(lot)
    return {'charge':charge,'days':days,'storage_target':target,'due':max(ZERO,financial['charged']+charge-financial['paid']),'boxes_after':lot.boxes-boxes,'gross_after':lot.gross-gross,'tare_after':lot.tare-tare}

@transaction.atomic
def receive(user,data):
    cam=Camera.objects.select_for_update().get(pk=data['camera'].pk)
    authorize(user,cam.organization_id,cam.pk,'receive')
    existing=Lot.objects.filter(create_key=data['request_key']).first()
    if existing:
        if existing.created_by_id!=user.pk:raise PermissionDenied
        return existing
    customer=Customer.objects.get(pk=data['customer'].pk)
    tariff=Tariff.objects.get(pk=data['tariff'].pk,is_active=True)
    if customer.organization_id!=cam.organization_id or tariff.organization_id!=cam.organization_id:raise PermissionDenied
    date_check(data['date'],data['date']);weights(data['boxes'],data['gross'],data['tare'])
    if cam.capacity_kg is not None:
        used=Lot.objects.filter(camera=cam,closed_on__isnull=True).aggregate(n=Sum('gross'))['n'] or ZERO
        if used+data['gross']>cam.capacity_kg:raise ValidationError('Kameraning brutto kg sig‘imi yetarli emas.')
    lot=Lot.objects.create(create_key=data['request_key'],organization=cam.organization,camera=cam,customer=customer,product=data['product'],variety=data['variety'],box_type=data['box_type'],received_on=data['date'],last_stock_date=data['date'],initial_boxes=data['boxes'],initial_gross=data['gross'],initial_tare=data['tare'],boxes=data['boxes'],gross=data['gross'],tare=data['tare'],tariff_name=tariff.name,service=tariff.service,basis=tariff.basis,rate=tariff.rate,storage_mode=tariff.storage_mode,bill_exit_day=tariff.bill_exit_day,**{f:getattr(tariff,f) for f in TIER_FIELDS},note=data['note'],created_by=user)
    Operation.objects.create(request_key=data['request_key'],lot=lot,camera=cam,kind='receive',date=data['date'],boxes=lot.boxes,gross=lot.gross,tare=lot.tare,boxes_after=lot.boxes,gross_after=lot.gross,tare_after=lot.tare,created_by=user)
    return lot

@transaction.atomic
def act(user,lot_id,kind,data,expected_snapshot=None):
    # Lock the lot before reading balances; duplicate submits reuse the committed operation.
    lot=Lot.objects.select_for_update().get(pk=lot_id)
    permission={'loss':'dispatch','storage_bill':'finance'}.get(kind,kind)
    authorize(user,lot.organization_id,lot.camera_id,permission)
    prior=Operation.objects.filter(request_key=data['request_key']).first()
    if prior:
        if prior.lot_id!=lot.pk or prior.kind!=kind:raise ValidationError('Hujjat kaliti boshqa amal uchun ishlatilgan.')
        return prior
    if expected_snapshot is not None and expected_snapshot != dispatch_snapshot(lot):
        raise ValidationError('Partiya qoldig‘i yoki hisob holati o‘zgargan. Hisobni qayta ko‘rib, yana tasdiqlang.')
    day=data['date'];date_check(day,lot.last_stock_date)
    amount=ZERO;charge=ZERO;days=0;boxes=0;gross=ZERO;tare=ZERO;target_cam=None
    if kind in ['dispatch','loss','storage_bill']:
        if kind!='storage_bill':boxes=data['boxes'];gross=data['gross'];tare=data['tare']
        result=quote(lot,kind,day,boxes,gross,tare);charge=result['charge'];days=result['days']
        amount=data.get('payment',ZERO)
        if amount<0:raise ValidationError('To‘lov manfiy bo‘lishi mumkin emas.')
        if amount:
            authorize(user,lot.organization_id,lot.camera_id,'payment')
        if kind=='dispatch' and result['due']>amount:
            authorize(user,lot.organization_id,lot.camera_id,'debt_dispatch')
        lot.boxes-=boxes;lot.gross-=gross;lot.tare-=tare
        lot.storage_billed=max(lot.storage_billed,result['storage_target'])
        if kind!='storage_bill' and lot.boxes==0:lot.closed_on=day
        lot.last_stock_date=day
    elif kind=='payment':
        amount=data['payment']
        if amount<=0:raise ValidationError('To‘lov 0 dan katta bo‘lishi kerak.')
    elif kind=='transfer':
        if lot.closed_on:raise ValidationError('Yopilgan partiyani ko‘chirish mumkin emas.')
        # Lock camera rows in stable order to serialize capacity allocation.
        dest_id=data['target_camera'].pk
        locked={c.pk:c for c in Camera.objects.select_for_update().filter(pk__in=[lot.camera_id,dest_id]).order_by('pk')}
        target_cam=locked[dest_id]
        authorize(user,lot.organization_id,target_cam.pk,'transfer')
        if target_cam.pk==lot.camera_id:raise ValidationError('Boshqa kamerani tanlang.')
        if target_cam.capacity_kg is not None:
            used=Lot.objects.filter(camera=target_cam,closed_on__isnull=True).aggregate(n=Sum('gross'))['n'] or ZERO
            if used+lot.gross>target_cam.capacity_kg:raise ValidationError('Qabul qiluvchi kamera sig‘imi yetarli emas.')
        boxes=lot.boxes;gross=lot.gross;tare=lot.tare
        lot.last_stock_date=day
    else:raise ValidationError('Noma’lum amal')
    op=Operation.objects.create(request_key=data['request_key'],lot=lot,camera_id=lot.camera_id,target_camera=target_cam,kind=kind,date=day,boxes=boxes,gross=gross,tare=tare,days=days,charge=charge,payment=amount,payment_method=data.get('payment_method',''),boxes_after=lot.boxes,gross_after=lot.gross,tare_after=lot.tare,note=data.get('note',''),created_by=user)
    if target_cam:lot.camera=target_cam
    lot.save()
    return op

@transaction.atomic
def reverse_last(user,op_id,key,reason):
    if not user.is_authenticated or not user.is_active or not user.is_superuser:raise PermissionDenied
    if not reason.strip():raise ValidationError('Bekor qilish sababini kiriting.')
    original=Operation.objects.get(pk=op_id)
    lot=Lot.objects.select_for_update().get(pk=original.lot_id)
    old=Operation.objects.filter(request_key=key).first()
    if old:
        if old.reversal_of_id!=original.pk:raise ValidationError('Kalit boshqa hujjatga tegishli.')
        return old
    if original.kind in ['receive','reversal']:raise ValidationError('Kirim va bekor qilish hujjatini bu amal bilan qaytarib bo‘lmaydi.')
    latest=lot.operations.order_by('-created_at').first()
    if latest.pk!=original.pk:raise ValidationError('Faqat partiyadagi eng oxirgi hujjatni bekor qilish mumkin.')
    if Operation.objects.filter(reversal_of=original).exists():raise ValidationError('Hujjat avval bekor qilingan.')
    if original.kind in ['dispatch','loss']:
        camera=Camera.objects.select_for_update().get(pk=lot.camera_id)
        if not camera.is_active:raise ValidationError('Avval kamerani faollashtiring.')
        if camera.capacity_kg is not None:
            used=Lot.objects.filter(camera=camera,closed_on__isnull=True).aggregate(n=Sum('gross'))['n'] or ZERO
            if used+original.gross>camera.capacity_kg:raise ValidationError('Qaytarish uchun kamera sig‘imi yetarli emas.')
        lot.boxes+=original.boxes;lot.gross+=original.gross;lot.tare+=original.tare;lot.closed_on=None
    if original.kind=='transfer':
        cams={c.pk:c for c in Camera.objects.select_for_update().filter(pk__in=[lot.camera_id,original.camera_id]).order_by('pk')}
        back=cams[original.camera_id]
        if not back.is_active:raise ValidationError('Avval oldingi kamerani faollashtiring.')
        if back.capacity_kg is not None:
            used=Lot.objects.filter(camera=back,closed_on__isnull=True).aggregate(n=Sum('gross'))['n'] or ZERO
            if used+lot.gross>back.capacity_kg:raise ValidationError('Oldingi kamera sig‘imi yetarli emas.')
        lot.camera=back
    if lot.service=='storage':lot.storage_billed=max(ZERO,lot.storage_billed-original.charge)
    lot.last_stock_date=timezone.localdate()
    reversal=Operation.objects.create(request_key=key,lot=lot,camera=original.camera,kind='reversal',reversal_of=original,date=timezone.localdate(),charge=-original.charge,payment=-original.payment,payment_method=original.payment_method,boxes_after=lot.boxes,gross_after=lot.gross,tare_after=lot.tare,note=reason,created_by=user)
    lot.save();return reversal
