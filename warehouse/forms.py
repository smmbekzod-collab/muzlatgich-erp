import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from core.access import cameras,organizations
from .models import Customer,Tariff

class RequestForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    date=forms.DateField(label='Sana',widget=forms.DateInput(attrs={'type':'date'}),initial=timezone.localdate)
    note=forms.CharField(label='Izoh / mashina / qabul qiluvchi',required=False,widget=forms.Textarea(attrs={'rows':2}))
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not self.is_bound:self.initial.setdefault('request_key',uuid.uuid4())

class IntakeForm(RequestForm):
    camera=forms.ModelChoiceField(label='Muzlatgich kamerasi',queryset=None)
    customer=forms.ModelChoiceField(label='Yuk egasi',queryset=Customer.objects.none())
    product=forms.CharField(label='Mahsulot',max_length=100)
    variety=forms.CharField(label='Nav',max_length=100,required=False)
    box_type=forms.CharField(label='Yashik turi',max_length=80)
    boxes=forms.IntegerField(label='Yashik soni',min_value=1)
    gross=forms.DecimalField(label='Brutto (gryaz), kg',min_value=Decimal('.001'),max_digits=14,decimal_places=3)
    tare=forms.DecimalField(label='Jami tara, kg',min_value=0,max_digits=14,decimal_places=3,help_text='Barcha yashiklar va qo‘shimcha qadoqning umumiy og‘irligi.')
    tariff=forms.ModelChoiceField(label='Xizmat tarifi',queryset=Tariff.objects.none())
    def __init__(self,user,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['camera'].queryset=cameras(user).filter(is_active=True,organization__is_active=True)
        orgs=organizations(user).filter(is_active=True)
        self.fields['customer'].queryset=Customer.objects.filter(organization__in=orgs)
        self.fields['tariff'].queryset=Tariff.objects.filter(organization__in=orgs,is_active=True)
    def clean(self):
        d=super().clean();cam=d.get('camera')
        for field in ['customer','tariff']:
            if cam and d.get(field) and d[field].organization_id!=cam.organization_id:self.add_error(field,'Kamera bilan bir tashkilotdan tanlang.')
        return d

class OperationForm(RequestForm):
    boxes=forms.IntegerField(label='Chiqariladigan yashik',min_value=1,required=False,widget=forms.NumberInput(attrs={'inputmode':'numeric','step':'1'}))
    gross=forms.DecimalField(label='Chiqariladigan brutto, kg',min_value=Decimal('.001'),max_digits=14,decimal_places=3,required=False,widget=forms.NumberInput(attrs={'inputmode':'decimal','step':'0.001'}))
    tare=forms.DecimalField(label='Chiqariladigan jami tara, kg',min_value=0,max_digits=14,decimal_places=3,required=False,widget=forms.NumberInput(attrs={'inputmode':'decimal','step':'0.001'}))
    payment=forms.DecimalField(label='Hozir olinadigan to‘lov, so‘m',min_value=0,max_digits=16,decimal_places=2,initial=0,required=False,widget=forms.NumberInput(attrs={'inputmode':'decimal','step':'0.01'}))
    payment_method=forms.ChoiceField(label='To‘lov turi',choices=[('cash','Naqd'),('bank','O‘tkazma'),('card','Karta')])
    target_camera=forms.ModelChoiceField(label='Qaysi kameraga',queryset=None,required=False)
    def __init__(self,user,lot,kind,*args,**kwargs):
        self.kind=kind
        super().__init__(*args,**kwargs)
        self.fields['target_camera'].queryset=cameras(user).filter(organization_id=lot.organization_id,is_active=True).exclude(pk=lot.camera_id)
        if kind not in ['dispatch','loss']:
            for name in ['boxes','gross','tare']:self.fields.pop(name)
        else:
            for name in ['boxes','gross','tare']:self.fields[name].required=True
            if kind=='loss':
                self.fields['boxes']=forms.IntegerField(label='Yo‘qotilgan yashik (yashik qolsa 0)',min_value=0,initial=0)
        if kind!='transfer':self.fields.pop('target_camera')
        else:
            self.fields['target_camera'].required=True
            for name in ['payment','payment_method']:self.fields.pop(name)
        if kind=='payment':self.fields['payment'].required=True
    def clean(self):
        d=super().clean()
        if 'payment' in self.fields:d['payment']=d.get('payment') or Decimal('0')
        return d

class CustomerForm(forms.Form):
    organization=forms.ModelChoiceField(label='Tashkilot',queryset=None)
    name=forms.CharField(label='Mijozning ismi / tashkiloti',max_length=150)
    phone=forms.CharField(label='Telefon',max_length=40,required=False)
    note=forms.CharField(label='Izoh',max_length=300,required=False)
    def __init__(self,user,*args,**kwargs):
        super().__init__(*args,**kwargs);self.fields['organization'].queryset=organizations(user).filter(is_active=True)

class TariffForm(forms.Form):
    camera=forms.ModelChoiceField(label='Tashkilotning kamerasi',queryset=None,help_text='Tarif shu tashkilotga tegishli bo‘ladi.')
    name=forms.CharField(label='Tarif nomi',max_length=120)
    service=forms.ChoiceField(label='Xizmat',choices=Tariff._meta.get_field('service').choices)
    basis=forms.ChoiceField(label='Sovutish vazni',choices=Tariff._meta.get_field('basis').choices)
    rate=forms.DecimalField(label='Eski tariflar uchun: so‘m/kg/kun yoki so‘m/oy',min_value=0,max_digits=16,decimal_places=2,required=False)
    tier_1_10=forms.DecimalField(label='1–10 kun: so‘m/kg',min_value=0,max_digits=16,decimal_places=2,required=False,initial=250)
    tier_11_15=forms.DecimalField(label='11–15 kun: so‘m/kg',min_value=0,max_digits=16,decimal_places=2,required=False,initial=300)
    tier_16_25=forms.DecimalField(label='16–25 kun: so‘m/kg',min_value=0,max_digits=16,decimal_places=2,required=False,initial=400)
    tier_26_30=forms.DecimalField(label='26–30 kun: so‘m/kg',min_value=0,max_digits=16,decimal_places=2,required=False,initial=450)
    tier_31_plus=forms.DecimalField(label='31 kundan so‘ng: so‘m/kg',min_value=0,max_digits=16,decimal_places=2,required=False,initial=450)
    storage_mode=forms.ChoiceField(label='Saqlama usuli',choices=Tariff._meta.get_field('storage_mode').choices)
    bill_exit_day=forms.BooleanField(label='Chiqish kuniga ham haq olinadi',required=False)
    def __init__(self,user,*args,**kwargs):
        super().__init__(*args,**kwargs);self.fields['camera'].queryset=cameras(user).filter(is_active=True,organization__is_active=True)

    def clean(self):
        d=super().clean()
        if d.get('service')=='tiered':
            for key in ['tier_1_10','tier_11_15','tier_16_25','tier_26_30','tier_31_plus']:
                if d.get(key) is None:
                    self.add_error(key,'Bu bosqichning narxini kiriting.')
            d['rate']=d.get('tier_1_10') or Decimal('0')
        else:
            if d.get('rate') is None:self.add_error('rate','Eski hisob usuli uchun narxni kiriting.')
            for key in ['tier_1_10','tier_11_15','tier_16_25','tier_26_30','tier_31_plus']:
                d[key]=None
        return d

class ExpenseForm(RequestForm):
    camera=forms.ModelChoiceField(label='Muzlatgich kamerasi',queryset=None)
    category=forms.ChoiceField(label='Xarajat turi',choices=[(x,x) for x in ['Elektr','Ish haqi','Ovqat','Qadoq','Transport','Ta’mir','Boshqa']])
    description=forms.CharField(label='Tavsif',max_length=300)
    amount=forms.DecimalField(label='Summa, so‘m',min_value=1,max_digits=16,decimal_places=2)
    def __init__(self,user,*args,**kwargs):
        super().__init__(*args,**kwargs);self.fields['camera'].queryset=cameras(user).filter(is_active=True,organization__is_active=True)
