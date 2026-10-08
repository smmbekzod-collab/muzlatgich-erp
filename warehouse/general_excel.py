"""Excel export for the existing overall financial report; read-only and permission-filtered upstream."""
from io import BytesIO
from decimal import Decimal
import xlsxwriter
from django.http import HttpResponse
from django.utils import timezone


def _safe(value):
    value = str(value if value is not None else '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value


def _sheet(book, name, title, subtitle, headings, widths, data, money_cols=(), numeric_cols=()):
    ws = book.add_worksheet(name)
    n = len(headings)
    dark = book.add_format({'font_name':'Calibri','font_size':18,'bold':True,'font_color':'white','bg_color':'#103E37','valign':'vcenter'})
    info = book.add_format({'font_name':'Calibri','font_size':11,'font_color':'#395B55','bg_color':'#EDF5F1','valign':'vcenter'})
    head = book.add_format({'font_name':'Calibri','bold':True,'font_color':'white','bg_color':'#1B6D59','border':1,'border_color':'#CFE2D9','text_wrap':True,'valign':'vcenter'})
    fmts = {}
    for k in ('text','money','number'):
        for odd in (False,True):
            fmts[(k,odd)] = book.add_format({'font_name':'Calibri','font_size':11,'border':1,'border_color':'#DEE9E5','bg_color':'#F0F7F4' if odd else '#FFFFFF','valign':'vcenter','num_format':'#,##0.00' if k=='money' else ('#,##0' if k=='number' else 'General')})
    ws.merge_range(0,0,0,n-1,title,dark); ws.set_row(0,38)
    ws.merge_range(1,0,1,n-1,subtitle,info); ws.set_row(1,26)
    for j,h in enumerate(headings):
        ws.write(3,j,h,head)
        ws.set_column(j,j,widths[j])
    ws.set_row(3,36)
    for i,record in enumerate(data):
        r=i+4; ws.set_row(r,23)
        for j,v in enumerate(record):
            kind='money' if j in money_cols else ('number' if j in numeric_cols else 'text')
            fmt=fmts[(kind,i%2==1)]
            if isinstance(v,(int,float,Decimal)) and not isinstance(v,bool):ws.write_number(r,j,float(v),fmt)
            else:ws.write_string(r,j,_safe(v),fmt)
    if not data:ws.merge_range(4,0,4,n-1,'Ushbu hisobot uchun ma’lumot topilmadi.',info)
    ws.autofilter(3,0,max(4,3+len(data)),n-1)
    ws.freeze_panes(4,1)
    ws.set_landscape();ws.fit_to_pages(1,0);ws.repeat_rows(3)
    ws.set_header('&CMUZLATGICH ERP')
    ws.set_footer('&LHisobot &CPagina &P / &N')
    return ws


def general_excel(rows, debts, start, end):
    output=BytesIO()
    book=xlsxwriter.Workbook(output, {'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False})
    organization_rows=[]
    for r in rows:
        cam=r['camera']
        organization_rows.append([cam.organization.name,cam.number,r['storage'],r['cooling'],r['paid'],r['expenses'],r['cash_net']])
    _sheet(book,'Kameralar hisoboti','MUZLATGICH ERP | UMUMIY MOLIYAVIY HISOBOT',
        f'Davr: {start:%d.%m.%Y} — {end:%d.%m.%Y}  |  Pul oqimi = tushum − xarajat (foyda emas)',
        ['Tashkilot','Kamera','Saqlash hisobi (so‘m)','Sovutish hisobi (so‘m)','Tushum (so‘m)','Xarajat (so‘m)','Sof pul oqimi (so‘m)'],
        [32,15,24,24,23,23,25],organization_rows,money_cols=(2,3,4,5,6))
    debt_rows=[]
    for r in debts:
        lot=r['lot']
        debt_rows.append([lot.short_id,lot.customer.name,lot.organization.name,lot.camera.number,lot.product,lot.variety,lot.boxes,lot.net,r['charged'],r['paid'],r['debt'],r['advance'],r['pending'],r['estimated_debt']])
    _sheet(book,'Partiyalar va qarzlar','MUZLATGICH ERP | JORIY PARTIYALAR VA QARZLAR',
        f'Joriy holat: {timezone.localdate():%d.%m.%Y}  |  Ushbu varaqda yuqoridagi sana filtri qo‘llanmaydi',
        ['Partiya','Mijoz','Tashkilot','Kamera','Mahsulot','Nav','Qolgan yashik','Qolgan sof kg','Yozilgan hisob (so‘m)','To‘lov (so‘m)','Qarz (so‘m)','Avans (so‘m)','Yozilmagan xizmat (so‘m)','Taxminiy qarz (so‘m)'],
        [18,28,29,15,20,20,18,19,24,20,20,20,27,26],debt_rows,money_cols=(8,9,10,11,12,13),numeric_cols=(6,7))
    book.close()
    response=HttpResponse(output.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition']=f'attachment; filename="muzlatgich-erp-umumiy-hisobot-{start:%Y%m%d}-{end:%Y%m%d}.xlsx"'
    response['Cache-Control']='private, no-store'
    return response
