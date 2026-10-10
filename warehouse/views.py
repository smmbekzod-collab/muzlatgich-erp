import csv,io,re
from decimal import Decimal
from datetime import date
import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.http import HttpResponse,JsonResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.db.models import Q,Sum
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET
from core import access
from .models import Lot,Operation,Customer,Tariff,Expense
from .customer_export import customer_csv
from .customer_excel import customer_excel, allowed_customers
from .general_excel import general_excel
from .forms import IntakeForm,OperationForm,CustomerForm,TariffForm,ExpenseForm,RequestForm
from .services import receive,act,quote,totals,pending,ZERO,date_check,reverse_last
from .dispatch_preview import make_dispatch_token, verify_dispatch_token

def visible_lots(user):return Lot.objects.filter(camera__in=access.cameras(user),organization__is_active=True).select_related('camera','camera__facility','organization','customer')
def allowed(user,lot,operation):
    try:access.authorize(user,lot.organization_id,lot.camera_id,operation);return True
    except PermissionDenied:return False
def context(request,**kw):return {'today':timezone.localdate(),**kw}
def form_error(form,error):
    for msg in error.messages if isinstance(error,ValidationError) else ['Bu amal uchun Sizda ruxsat yo‘q.']:form.add_error(None,msg)

@login_required
def dashboard(request):
    """Branch-aware overview; all rows are scoped by access.cameras on the server."""
    allowed_cameras = list(access.cameras(request.user).select_related('organization', 'facility')
                           .order_by('organization__name', 'facility__name', 'number'))
    facility_map = {cam.facility_id: cam.facility for cam in allowed_cameras if cam.facility_id}
    facility_options = sorted(facility_map.values(), key=lambda f: (f.organization.name, f.name))
    selected_facility = request.GET.get('facility', '')
    if selected_facility and selected_facility.isdecimal():
        if int(selected_facility) in facility_map:
            allowed_cameras = [cam for cam in allowed_cameras if cam.facility_id == int(selected_facility)]
        else:
            allowed_cameras = []  # Unknown or unauthorized filters reveal nothing.
    elif selected_facility:
        allowed_cameras = []
    selected = request.GET.get('camera', '')
    if selected and selected.isdecimal():
        allowed_cameras = [cam for cam in allowed_cameras if cam.pk == int(selected)]
    elif selected:
        allowed_cameras = []

    camera_ids = [cam.pk for cam in allowed_cameras]
    from django.db.models import Count
    active_totals = Lot.objects.filter(camera_id__in=camera_ids, closed_on__isnull=True).values('camera_id').annotate(
        boxes_total=Sum('boxes'), gross_total=Sum('gross'), tare_total=Sum('tare'), lot_count=Count('pk'))
    by_camera = {row['camera_id']: row for row in active_totals}
    summary = []
    total_boxes = 0
    total_net = ZERO
    total_gross = ZERO
    for cam in allowed_cameras:
        values = by_camera.get(cam.pk, {})
        boxes = values.get('boxes_total') or 0
        gross = values.get('gross_total') or ZERO
        tare = values.get('tare_total') or ZERO
        net = gross - tare
        total_boxes += boxes
        total_net += net
        total_gross += gross
        capacity = cam.capacity_kg
        usage = int(gross * 100 / capacity) if capacity and capacity > 0 else None
        fullness = min(100, usage) if usage is not None else None
        summary.append({'camera':cam, 'boxes':boxes, 'gross':gross, 'net':net,
                        'lot_count':values.get('lot_count') or 0, 'fill_percent':fullness,
                        'utilization_percent':usage,
                        'capacity':capacity, 'free_kg':max(ZERO, capacity - gross) if capacity is not None else None})

    lots = visible_lots(request.user).filter(camera_id__in=camera_ids)
    query = request.GET.get('q', '').strip()[:120]
    if query:
        lots = lots.filter(Q(product__icontains=query) | Q(customer__name__icontains=query) | Q(variety__icontains=query))
    status = request.GET.get('status', 'open')
    if status != 'all':
        status = 'open'
        lots = lots.filter(closed_on__isnull=True)
    return render(request, 'warehouse/dashboard.html', context(request,
        lots=lots.order_by('-created_at')[:300], summary=summary, query=query,
        camera_options=access.cameras(request.user).select_related('organization','facility'),
        facility_options=facility_options, selected_facility=selected_facility,
        selected=selected, status=status, total_boxes=total_boxes,
        total_net=total_net, total_gross=total_gross, camera_count=len(summary),
        active_lot_count=sum(x['lot_count'] for x in summary)))

@login_required
def intake(request):
    form=IntakeForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:lot=receive(request.user,form.cleaned_data)
        except (ValidationError,PermissionDenied) as e:form_error(form,e)
        else:messages.success(request,'Yuk qabul qilindi. QR yorliqni chop etishingiz mumkin.');return redirect('lot',pk=lot.pk)
    return render(request,'warehouse/form.html',context(request,form=form,title='Yuk qabul qilish',submit='Qabul qilish',help='Bir partiya — bir kelish sanasi, egasi, nav va tarif. Qo‘shimcha kelgan yukni yangi partiya sifatida kiriting.'))

@login_required
def lot_detail(request,pk):
    lot=get_object_or_404(visible_lots(request.user),pk=pk)
    perms={name:allowed(request.user,lot,name) for name in access.OPERATIONS}
    financial=totals(lot) if perms['finance'] or perms['payment'] or perms['dispatch'] else None
    return render(request,'warehouse/lot.html',context(request,lot=lot,perms=perms,financial=financial,pending=pending(lot) if financial is not None else None,operations=lot.operations.select_related('created_by','camera','target_camera')[:200]))

@login_required
def operation(request,pk,kind):
    if kind not in ['dispatch','loss','transfer','payment','storage_bill']:
        raise PermissionDenied
    lot=get_object_or_404(visible_lots(request.user),pk=pk)
    access.authorize(request.user,lot.organization_id,lot.camera_id,{'loss':'dispatch','storage_bill':'finance'}.get(kind,kind))
    form=OperationForm(request.user,lot,kind,request.POST or None)
    preview=None
    preview_token=None
    titles={'dispatch':'Yuk chiqarish','loss':'Yo‘qotishni qayd etish','transfer':'Qoldiqni boshqa kameraga ko‘chirish','payment':'To‘lov olish','storage_bill':'Saqlama hisobini yozish'}
    if request.method=='POST' and form.is_valid():
        try:
            if request.POST.get('confirm')=='yes':
                expected=None
                if kind=='dispatch':
                    expected=verify_dispatch_token(request.user,lot,form.cleaned_data,request.POST.get('preview_token',''))
                op=act(request.user,pk,kind,form.cleaned_data,expected_snapshot=expected)
                messages.success(request,'Hujjat tasdiqlandi. Qoldiq va hisob yangilandi.')
                return redirect('receipt',pk=op.pk)
            if kind in ['dispatch','loss','storage_bill']:
                d=form.cleaned_data
                preview=quote(lot,kind,d['date'],d.get('boxes',0),d.get('gross',ZERO),d.get('tare',ZERO))
                preview['pay_now']=d.get('payment',ZERO)
                preview['due_after']=max(ZERO,preview['due']-preview['pay_now'])
                if kind=='dispatch':
                    preview_token=make_dispatch_token(request.user,lot,d)
            else:
                preview={'simple':True,'kind':kind,'data':form.cleaned_data}
        except (ValidationError,PermissionDenied) as e:
            form_error(form,e)
    return render(request,'warehouse/operation.html',context(request,form=form,lot=lot,title=titles[kind],
                  kind=kind,preview=preview,preview_token=preview_token))

@login_required
@require_GET
def qr_image(request,pk):
    lot=get_object_or_404(visible_lots(request.user),pk=pk)
    value=request.build_absolute_uri(reverse('lot',args=[lot.pk]))
    image=qrcode.make(value);buf=io.BytesIO();image.save(buf,format='PNG')
    response=HttpResponse(buf.getvalue(),content_type='image/png');response['Cache-Control']='private, no-store';return response

@login_required
def label(request,pk):
    lot=get_object_or_404(visible_lots(request.user),pk=pk)
    return render(request,'warehouse/label.html',context(request,lot=lot))

@login_required
def scanner(request):
    return render(request,'warehouse/scanner.html')

@login_required
def receipt(request,pk):
    op=get_object_or_404(Operation.objects.select_related('lot','lot__customer','lot__organization','camera','target_camera','created_by').filter(lot__in=visible_lots(request.user)),pk=pk)
    show_money=any(allowed(request.user,op.lot,x) for x in ['finance','payment','dispatch'])
    return render(request,'warehouse/receipt.html',context(request,op=op,show_money=show_money))

@login_required
def customers(request):
    form=CustomerForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        permitted=request.user.is_superuser or access.memberships(request.user).filter(organization=d['organization']).filter(Q(can_receive=True)|Q(can_take_payment=True)).exists()
        if not permitted:raise PermissionDenied
        Customer.objects.create(**d);messages.success(request,'Mijoz qo‘shildi.');return redirect('customers')
    rows=Customer.objects.filter(organization__in=access.organizations(request.user)).select_related('organization').order_by('name')
    return render(request,'warehouse/catalog.html',context(request,form=form,rows=rows,title='Mijozlar',catalog='customers'))

@login_required
def reverse_operation(request,pk):
    if not request.user.is_superuser:raise PermissionDenied
    op=get_object_or_404(Operation,pk=pk)
    form=RequestForm(request.POST or None)
    form.fields.pop('date')
    form.fields['note'].required=True
    form.fields['note'].label='Bekor qilish sababi'
    if request.method=='POST' and form.is_valid():
        try:undo=reverse_last(request.user,pk,form.cleaned_data['request_key'],form.cleaned_data['note'])
        except (ValidationError,PermissionDenied) as e:form_error(form,e)
        else:messages.success(request,'Teskari hujjat yozildi. Asl hujjat tarixda saqlandi.');return redirect('receipt',pk=undo.pk)
    return render(request,'warehouse/form.html',context(request,form=form,title='Oxirgi hujjatni bekor qilish',submit='Bekor qilishni tasdiqlash',help=f'{op.short_id}: miqdor, xizmat haqi va yozilgan to‘lov qaytariladi. Pul haqiqatda qaytarilgan yoki noto‘g‘ri qayd etilgan bo‘lishi kerak.'))

@login_required
def tariffs(request):
    form=TariffForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data;cam=d.pop('camera')
        try:access.authorize(request.user,cam.organization_id,cam.pk,'tariff')
        except PermissionDenied as e:form_error(form,e)
        else:Tariff.objects.create(organization=cam.organization,created_by=request.user,**d);messages.success(request,'Yangi tarif saqlandi. Eski yuklar tarifi o‘zgarmaydi.');return redirect('tariffs')
    rows=Tariff.objects.filter(organization__in=access.organizations(request.user)).select_related('organization').order_by('-created_at')
    return render(request,'warehouse/catalog.html',context(request,form=form,rows=rows,title='Tariflar',catalog='tariffs'))

@login_required
def expenses(request):
    form=ExpenseForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        try:
            cam=d['camera'];access.authorize(request.user,cam.organization_id,cam.pk,'expense');date_check(d['date'],d['date'])
            Expense.objects.get_or_create(request_key=d['request_key'],defaults={'organization':cam.organization,'camera':cam,'date':d['date'],'category':d['category'],'description':d['description'],'amount':d['amount'],'created_by':request.user})
        except (ValidationError,PermissionDenied) as e:form_error(form,e)
        else:messages.success(request,'Xarajat saqlandi.');return redirect('report')
    return render(request,'warehouse/form.html',context(request,form=form,title='Xarajat kiritish',submit='Saqlash'))

@login_required
def report(request):
    start=timezone.localdate().replace(day=1);end=timezone.localdate()
    try:
        if request.GET.get('start'):start=date.fromisoformat(request.GET['start'])
        if request.GET.get('end'):end=date.fromisoformat(request.GET['end'])
        if start>end:raise ValueError
    except ValueError:return HttpResponse('Sana oralig‘i noto‘g‘ri.',status=400)
    visible=[]
    for cam in access.cameras(request.user).filter(organization__is_active=True):
        try:access.authorize(request.user,cam.organization_id,cam.pk,'finance');visible.append(cam)
        except PermissionDenied:pass
    if not visible:raise PermissionDenied('Moliyaviy hisobot huquqi kerak.')
    rows=[]
    for cam in visible:
        ledger=Operation.objects.filter(camera=cam,date__range=[start,end]);spend=Expense.objects.filter(camera=cam,date__range=[start,end]).aggregate(s=Sum('amount'))['s'] or ZERO
        cooling=ledger.filter(lot__service='cooling').aggregate(s=Sum('charge'))['s'] or ZERO
        storage=ledger.filter(lot__service='storage').aggregate(s=Sum('charge'))['s'] or ZERO
        paid=ledger.aggregate(s=Sum('payment'))['s'] or ZERO
        rows.append({'camera':cam,'cooling':cooling,'storage':storage,'paid':paid,'expenses':spend,'cash_net':paid-spend})
    debts=[]
    for lot in visible_lots(request.user).filter(camera__in=visible).order_by('customer__name'):
        t=totals(lot);p=pending(lot)
        debts.append({'lot':lot,**t,'pending':p,'estimated_debt':max(ZERO,t['charged']+p-t['paid'])})
    if request.GET.get('export')=='xlsx':
        return general_excel(rows, debts, start, end)
    if request.GET.get('export')=='csv':
        response=HttpResponse(content_type='text/csv; charset=utf-8-sig');response['Content-Disposition']='attachment; filename="muzlatgich-erp-hisobot.csv"';response.write('\ufeff')
        writer=csv.writer(response);writer.writerow(['Tashkilot','Kamera','Sovutish hisob','Saqlama hisob','Tushum','Xarajat','Pul oqimi','Davr boshi','Davr oxiri'])
        def safe(x):
            text=str(x);return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
        for row in rows:writer.writerow([safe(row['camera'].organization.name),row['camera'].number,row['cooling'],row['storage'],row['paid'],row['expenses'],row['cash_net'],start,end])
        writer.writerow([]);writer.writerow(['Partiya','Mijoz','Tasdiqlangan hisob','To‘lov','Qarz','Avans','Hali yozilmagan xizmat','Joriy taxminiy qarz'])
        for row in debts:writer.writerow([row['lot'].short_id,safe(row['lot'].customer.name),row['charged'],row['paid'],row['debt'],row['advance'],row['pending'],row['estimated_debt']])
        return response
    return render(request,'warehouse/report.html',context(request,rows=rows,debts=debts,start=start,end=end,report_customers=allowed_customers(request.user)))

def manifest(request):return JsonResponse({'name':'Muzlatgich ERP','short_name':'Muzlatgich ERP','start_url':'/app/','display':'standalone','background_color':'#f4f7fa','theme_color':'#113d36','icons':[{'src':'/static/warehouse/icon-192.png','sizes':'192x192','type':'image/png'},{'src':'/static/warehouse/icon-512.png','sizes':'512x512','type':'image/png'}]})
def service_worker(request):
    # Never cache financial/authenticated responses or replay offline mutations.
    return HttpResponse("self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));",content_type='application/javascript')

@login_required
def rentals(request):
    from uuid import uuid4, UUID
    from django.db.models import Q
    from .models import CameraRentalAgreement
    from .forms import CameraRentalForm
    from .services import (open_camera_rental,issue_camera_rental_invoice,
        pay_camera_rental_invoice,change_camera_rental_rate,next_camera_rental_month)
    permitted=[]
    for camera in access.cameras(request.user).filter(organization__is_active=True):
        if any(allowed_camera_permission(request.user,camera,perm) for perm in ['tariff','payment','finance']):
            permitted.append(camera.pk)
    agreements=CameraRentalAgreement.objects.filter(camera_id__in=permitted).select_related(
        'camera','camera__facility','camera__organization','customer').prefetch_related('invoices__payments','rate_changes')
    form=CameraRentalForm(request.user,request.POST if request.method=='POST' and request.POST.get('action')=='create' else None)
    errors=[]
    if request.method=='POST':
        try:
            action=request.POST.get('action','')
            if action=='create':
                if form.is_valid():
                    open_camera_rental(request.user,form.cleaned_data)
                    messages.success(request,'Oylik kamera ijarasi saqlandi.')
                    return redirect('rentals')
            elif action=='bill':
                invoice=issue_camera_rental_invoice(request.user,int(request.POST.get('agreement_id','')),
                    UUID(request.POST.get('request_key','')))
                messages.success(request,'Kamera ijarasi uchun oylik hisob chiqarildi.')
                return redirect('rental_invoice',pk=invoice.pk)
            elif action=='payment':
                p=pay_camera_rental_invoice(request.user,int(request.POST.get('invoice_id','')),
                    UUID(request.POST.get('request_key','')),
                    Decimal(request.POST.get('amount','')),request.POST.get('method',''),timezone.localdate())
                messages.success(request,'Ijara to‘lovi qayd etildi.')
                return redirect('rental_invoice',pk=p.invoice_id)
            elif action=='rate':
                change_camera_rental_rate(request.user,int(request.POST.get('agreement_id','')),
                    Decimal(request.POST.get('monthly_rate','')),date.fromisoformat(request.POST.get('effective_from','')))
                messages.success(request,'Keyingi oy narxi belgilandi. Eski hisoblar o‘zgarmaydi.')
                return redirect('rentals')
            else:errors.append('Noma’lum amal.')
        except (ValidationError,PermissionDenied,ValueError,TypeError,ArithmeticError) as e:
            errors.extend(e.messages if isinstance(e,ValidationError) else ['Ma’lumot xato yoki ruxsat yetarli emas.'])
    rows=[]
    for agreement in agreements:
        can_tariff=allowed_camera_permission(request.user,agreement.camera,'tariff')
        can_payment=allowed_camera_permission(request.user,agreement.camera,'payment')
        next_date=next_camera_rental_month(agreement)
        in_term=not agreement.end_on or next_date<=agreement.end_on
        rows.append({'agreement':agreement,'invoices':list(agreement.invoices.all()),
           'next_date':next_date,'can_tariff':can_tariff,'can_payment':can_payment,
           'can_bill':can_tariff and in_term and next_date<=timezone.localdate(),
           'can_change':can_tariff and in_term and next_date>=timezone.localdate() and
                         not agreement.rate_changes.filter(effective_from=next_date).exists()})
    return render(request,'warehouse/rentals.html',context(request,form=form,rows=rows,
        form_errors=errors,request_key=uuid4()))

def allowed_camera_permission(user,camera,capability):
    try:
        access.authorize(user,camera.organization_id,camera.pk,capability)
        return True
    except PermissionDenied:
        return False

@login_required
def rental_invoice(request,pk):
    from .models import CameraRentalInvoice
    invoice=get_object_or_404(CameraRentalInvoice.objects.select_related(
         'agreement__camera','agreement__camera__facility','agreement__camera__organization',
         'agreement__customer','created_by').filter(
         agreement__camera__in=access.cameras(request.user)),pk=pk)
    if not any(allowed_camera_permission(request.user,invoice.agreement.camera,perm)
               for perm in ['tariff','payment','finance']):
        raise PermissionDenied
    return render(request,'warehouse/rental_invoice.html',context(request,invoice=invoice,
        payments=invoice.payments.select_related('created_by'),paid=invoice.paid,debt=invoice.debt))
