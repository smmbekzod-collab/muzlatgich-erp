"""Read-only customer-specific formatted Excel report; all authorization stays server-side."""
from io import BytesIO
from decimal import Decimal
import xlsxwriter
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from core import access
from .models import Lot, Operation
from .services import pending, ZERO


def financial_cameras(user):
    ids = []
    for camera in access.cameras(user).filter(is_active=True, organization__is_active=True):
        try:
            access.authorize(user, camera.organization_id, camera.pk, 'finance')
            ids.append(camera.pk)
        except PermissionDenied:
            pass
    return ids


def allowed_customers(user):
    ids = financial_cameras(user)
    if not ids:
        raise PermissionDenied('Moliyaviy hisobot huquqi kerak.')
    return (Lot.objects.filter(camera_id__in=ids, organization__is_active=True)
            .values('customer_id', 'customer__name', 'organization__name')
            .distinct().order_by('customer__name', 'organization__name', 'customer_id'))


def excel_text(value):
    s = str(value if value is not None else '')
    # Never interpret untrusted user input as an Excel formula.
    return "'" + s if s.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else s


def write_table(ws, title, headers, rows, widths, book, money_columns=(), count_columns=()):
    end = len(headers) - 1
    top = book.add_format({'bold': True, 'font_size': 16, 'font_color': '#FFFFFF', 'bg_color': '#123E38', 'valign':'vcenter'})
    head = book.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#176653', 'border': 1,'border_color':'#D8E7E1','text_wrap':True,'valign':'vcenter'})
    plain = book.add_format({'border':1,'border_color':'#E1E8E6','valign':'vcenter'})
    alternate = book.add_format({'border':1,'border_color':'#E1E8E6','bg_color':'#F0F7F4','valign':'vcenter'})
    amt = book.add_format({'border':1,'border_color':'#E1E8E6','num_format':'#,##0.00','valign':'vcenter'})
    amt_alt = book.add_format({'border':1,'border_color':'#E1E8E6','bg_color':'#F0F7F4','num_format':'#,##0.00','valign':'vcenter'})
    integer = book.add_format({'border':1,'border_color':'#E1E8E6','num_format':'#,##0','valign':'vcenter'})
    integer_alt = book.add_format({'border':1,'border_color':'#E1E8E6','bg_color':'#F0F7F4','num_format':'#,##0','valign':'vcenter'})
    ws.merge_range(0,0,0,end,title,top);ws.set_row(0,34)
    ws.merge_range(1,0,1,end,'Tuzilgan sana: '+timezone.localdate().isoformat()+'  |  Ma’lumotlar faqat tanlangan mijoz bo‘yicha',plain)
    ws.set_row(3,34)
    for i,h in enumerate(headers): ws.write(3,i,h,head); ws.set_column(i,i,widths[i] if i < len(widths) else 18)
    for r,record in enumerate(rows,4):
        ws.set_row(r,23)
        for c,v in enumerate(record):
            fmt=(amt_alt if r%2 else amt) if c in money_columns else ((integer_alt if r%2 else integer) if c in count_columns else (alternate if r%2 else plain))
            if isinstance(v,(int,float,Decimal)) and not isinstance(v,bool): ws.write_number(r,c,float(v),fmt)
            else: ws.write_string(r,c,excel_text(v),fmt)
    ws.freeze_panes(4,3)
    ws.autofilter(3,0,max(4,3+len(rows)),end)
    ws.fit_to_pages(1,0);ws.set_landscape();ws.repeat_rows(3)


@login_required
def customer_excel(request):
    cameras = financial_cameras(request.user)
    if not cameras: raise PermissionDenied('Moliyaviy hisobot huquqi kerak.')
    customer_id = request.GET.get('customer','').strip()
    if not customer_id.isdecimal():
        return HttpResponse('Avval mijozni tanlang.',status=400)
    lots=list(Lot.objects.filter(camera_id__in=cameras, organization__is_active=True, customer_id=int(customer_id))
              .select_related('organization','camera','customer').order_by('received_on','pk'))
    if not lots: raise PermissionDenied('Tanlangan mijoz ma’lumotlariga ruxsat yo‘q.')
    ops = Operation.objects.filter(lot__in=lots).select_related('lot','camera','target_camera','created_by','reversal_of').order_by('date','created_at','pk')
    by_lot={}
    for op in ops:by_lot.setdefault(op.lot_id,[]).append(op)
    kinds=dict(Operation._meta.get_field('kind').choices)
    party_rows=[]; activity_rows=[]
    grand_charge=grand_paid=grand_due=grand_advance=grand_boxes=grand_out=Decimal('0')
    for lot in lots:
        history=by_lot.get(lot.pk,[])
        charge=sum((x.charge for x in history),ZERO);paid=sum((x.payment for x in history),ZERO)
        due=max(ZERO,charge-paid);adv=max(ZERO,paid-charge)
        reversed_ids={x.reversal_of_id for x in history if x.reversal_of_id}
        dispatches=[x for x in history if x.kind=='dispatch' and x.pk not in reversed_ids]
        out_boxes=sum((x.boxes for x in dispatches),0)
        grand_charge+=charge;grand_paid+=paid;grand_due+=due;grand_advance+=adv;grand_boxes+=lot.boxes;grand_out+=out_boxes
        party_rows.append([lot.short_id,lot.customer.name,lot.organization.name,lot.camera.number,lot.received_on,lot.closed_on or '',lot.product,lot.variety,lot.box_type,lot.initial_boxes,out_boxes,lot.boxes,lot.initial_gross-lot.initial_tare,lot.net,lot.tariff_name,lot.rate,charge,paid,due,adv,pending(lot),lot.note])
        for x in history:
            activity_rows.append([lot.customer.name,lot.short_id,x.date,kinds.get(x.kind,x.kind),x.camera.number,x.target_camera.number if x.target_camera else '',x.boxes,x.gross,x.tare,x.net,x.boxes_after,x.charge,x.payment,x.payment_method,x.created_by.username,x.note,x.short_id,x.reversal_of.short_id if x.reversal_of_id else ''])
    data=BytesIO();book=xlsxwriter.Workbook(data,{'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False})
    summary=book.add_worksheet('Mijoz xulosasi');detail=book.add_worksheet('Partiyalar');moves=book.add_worksheet('Harakatlar va tolovlar')
    dark=book.add_format({'bold':True,'font_size':18,'font_color':'#FFFFFF','bg_color':'#123E38'})
    label=book.add_format({'bold':True,'font_color':'#176653','bg_color':'#F0F7F4','border':1,'border_color':'#D5E6DE'})
    value=book.add_format({'border':1,'border_color':'#D5E6DE'})
    num=book.add_format({'border':1,'border_color':'#D5E6DE','num_format':'#,##0.00'})
    summary.merge_range('A1:F1','MUZLATGICH ERP | MIJOZ HISOBOTI',dark);summary.set_row(0,38)
    summary.set_column('A:A',28);summary.set_column('B:B',27);summary.set_column('C:F',19)
    for row,head,val in [(3,'Mijoz',lots[0].customer.name),(4,'Telefon',lots[0].customer.phone),(5,'Hisobot sanasi',str(timezone.localdate())),(7,'Partiyalar soni',len(lots)),(8,'Joriy yashiklar',grand_boxes),(9,'Jami chiqarilgan yashiklar',grand_out),(10,'Yozilgan xizmat haqi (so‘m)',grand_charge),(11,'To‘lovlar (so‘m)',grand_paid),(12,'Qarz (so‘m)',grand_due),(13,'Avans / haqdorlik (so‘m)',grand_advance)]:
        summary.write(row,0,head,label)
        if isinstance(val,(int,float,Decimal)): summary.write_number(row,1,float(val),num)
        else: summary.write_string(row,1,excel_text(val),value)
    summary.merge_range('A17:F17','Izoh: Qarz va avans tasdiqlangan hujjatlar bo‘yicha. Hali yozilmagan xizmat Partiyalar varag‘ida alohida.',value)
    write_table(detail,'PARTIYALAR VA JORIY QOLDIQ', ['Partiya','Mijoz','Tashkilot','Kamera','Kirim sanasi','Yopilgan sana','Mahsulot','Nav','Yashik turi','Kirim yashik','Chiqim yashik','Qolgan yashik','Kirim sof kg','Qolgan sof kg','Tarif','Narx (so‘m)','Hisob (so‘m)','To‘langan (so‘m)','Qarz (so‘m)','Avans (so‘m)','Yozilmagan xizmat (so‘m)','Izoh'],party_rows,[17,25,25,12,16,16,18,18,16,15,15,15,18,18,20,18,19,19,19,19,24,35],book,money_columns=(12,13,15,16,17,18,19,20),count_columns=(9,10,11))
    write_table(moves,'YUK HARAKATLARI VA TO‘LOVLAR', ['Mijoz','Partiya','Sana','Amal','Kamera','Manzil kamera','Yashik','Brutto kg','Tara kg','Sof kg','Qoldiq yashik','Xizmat haqi (so‘m)','To‘lov (so‘m)','To‘lov usuli','Xodim','Izoh','Hujjat ID','Bekor hujjat ID'],activity_rows,[25,17,16,18,13,19,12,17,16,17,17,21,19,19,22,35,17,19],book,money_columns=(7,8,9,11,12),count_columns=(6,10))
    book.close();data.seek(0)
    response=HttpResponse(data.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition']='attachment; filename="muzlatgich-mijoz-%s.xlsx"'%int(customer_id)
    return response
