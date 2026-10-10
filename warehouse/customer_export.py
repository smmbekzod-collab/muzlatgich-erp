"""Read-only, permission-filtered client-level CSV export. No schema changes."""
import csv
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from core import access
from .models import Lot, Operation
from .services import pending, ZERO


def cell(value):
    """Prevent Excel formula injection in user-editable cells."""
    s = str(value if value is not None else '')
    return "'" + s if s.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else s


@login_required
def customer_csv(request):
    cameras = []
    for camera in access.cameras(request.user).filter(organization__is_active=True):
        try:
            access.authorize(request.user, camera.organization_id, camera.pk, 'finance')
            cameras.append(camera.pk)
        except PermissionDenied:
            pass
    if not cameras:
        raise PermissionDenied('Moliyaviy hisobot huquqi kerak.')
    lots = Lot.objects.filter(camera_id__in=cameras, organization__is_active=True).select_related('organization', 'camera', 'customer').order_by('organization__name','customer__name','received_on','pk')
    customer = request.GET.get('customer','').strip()
    if customer:
        if not customer.isdigit():
            return HttpResponse('Mijoz ID noto‘g‘ri.',status=400)
        lots = lots.filter(customer_id=int(customer))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="muzlatgich-mijozlar-batafsil.csv"'
    response.write('\ufeff')
    w = csv.writer(response)
    w.writerow(['MIJOZLAR BO‘YICHA BATAFSIL HISOBOT','Tuzilgan sana',timezone.localdate().isoformat()])
    w.writerow(['Izoh','Barcha sanalar bo‘yicha tarix; amaldagi qoldiq va hisoblar bugungi holatga.'])
    w.writerow([])
    w.writerow(['PARTIYALAR VA MIJOZ QOLDIQLARI'])
    w.writerow(['Tashkilot','Mijoz','Telefon','Mijoz izohi','Partiya','Kamera (joriy)','Kirim sanasi','Yopilgan sana','Mahsulot','Nav','Yashik turi','Dastlabki yashik','Dastlabki brutto kg','Dastlabki tara kg','Dastlabki sof kg','Jami chiqim yashik','Jami chiqim brutto kg','Jami chiqim tara kg','Jami chiqim sof kg','Hozirgi yashik','Hozirgi brutto kg','Hozirgi tara kg','Hozirgi sof kg','Tarif nomi','Xizmat turi','Hisob birligi','Narx','Hisoblangan xizmat so‘m','To‘langan so‘m','Qarz so‘m','Haqdorlik/avans so‘m','Hali yozilmagan xizmat so‘m','Taxminiy qarz so‘m','Partiya izohi'])
    all_lots = list(lots)
    operations = Operation.objects.filter(lot__in=all_lots).select_related('camera','target_camera','created_by','lot').order_by('date','created_at','pk')
    by_lot = {}
    for op in operations:
        by_lot.setdefault(op.lot_id,[]).append(op)
    kind_labels = dict(Operation._meta.get_field('kind').choices)
    for lot in all_lots:
        ops=by_lot.get(lot.pk,[])
        charge=sum((op.charge for op in ops),ZERO)
        paid=sum((op.payment for op in ops),ZERO)
        due=max(ZERO,charge-paid)
        advance=max(ZERO,paid-charge)
        unbilled=pending(lot)
        reversed_ids={op.reversal_of_id for op in ops if op.reversal_of_id}
        dispatches=[op for op in ops if op.kind=='dispatch' and op.pk not in reversed_ids]
        # Reversed transactions are represented by a reversal entry in the full activity history.
        out_boxes=sum((op.boxes for op in dispatches),0)
        out_gross=sum((op.gross for op in dispatches),ZERO)
        out_tare=sum((op.tare for op in dispatches),ZERO)
        w.writerow([cell(lot.organization.name),cell(lot.customer.name),cell(lot.customer.phone),cell(lot.customer.note),lot.short_id,lot.camera.number,lot.received_on,lot.closed_on or '',cell(lot.product),cell(lot.variety),cell(lot.box_type),lot.initial_boxes,lot.initial_gross,lot.initial_tare,lot.initial_gross-lot.initial_tare,out_boxes,out_gross,out_tare,out_gross-out_tare,lot.boxes,lot.gross,lot.tare,lot.net,cell(lot.tariff_name),cell(lot.get_service_display()) if hasattr(lot,'get_service_display') else lot.service,lot.basis,cell(lot.rate_description),charge,paid,due,advance,unbilled,max(ZERO,charge+unbilled-paid),cell(lot.note)])
    w.writerow([])
    w.writerow(['HAR BIR HARAKAT TARIXI'])
    w.writerow(['Tashkilot','Mijoz','Telefon','Partiya','Sana','Amal','Kamera','Ko‘chirilgan kamera','Yashik soni','Brutto kg','Tara kg','Sof kg','Amaldan keyingi yashik','Amaldan keyingi brutto kg','Amaldan keyingi tara kg','Hisoblangan so‘m','To‘langan so‘m','To‘lov usuli','Izoh','Kiritgan xodim','Hujjat ID','Bekor qilingan hujjat ID'])
    for lot in all_lots:
        for op in by_lot.get(lot.pk,[]):
            w.writerow([cell(lot.organization.name),cell(lot.customer.name),cell(lot.customer.phone),lot.short_id,op.date,kind_labels.get(op.kind,op.kind),op.camera.number,op.target_camera.number if op.target_camera else '',op.boxes,op.gross,op.tare,op.net,op.boxes_after,op.gross_after,op.tare_after,op.charge,op.payment,cell(op.payment_method),cell(op.note),cell(op.created_by.username),op.short_id,op.reversal_of.short_id if op.reversal_of_id else ''])
    return response
