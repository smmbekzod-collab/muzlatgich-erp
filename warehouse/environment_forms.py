"""Manual environmental monitoring forms. No automatic sensor ingestion in this phase."""
from datetime import timedelta
from django import forms
from django.utils import timezone
from .models import CameraEnvironmentPolicy, CameraEnvironmentReading


class CameraEnvironmentPolicyForm(forms.ModelForm):
    class Meta:
        model = CameraEnvironmentPolicy
        fields = (
            'min_temperature', 'max_temperature', 'min_humidity', 'max_humidity',
            'check_interval_hours', 'max_storage_days'
        )
        widgets = {
            'min_temperature': forms.NumberInput(attrs={'step':'0.01','inputmode':'decimal','placeholder':'masalan: -1'}),
            'max_temperature': forms.NumberInput(attrs={'step':'0.01','inputmode':'decimal','placeholder':'masalan: 2'}),
            'min_humidity': forms.NumberInput(attrs={'step':'0.01','min':0,'max':100,'inputmode':'decimal'}),
            'max_humidity': forms.NumberInput(attrs={'step':'0.01','min':0,'max':100,'inputmode':'decimal'}),
            'check_interval_hours': forms.NumberInput(attrs={'min':1,'max':168,'inputmode':'numeric'}),
            'max_storage_days': forms.NumberInput(attrs={'min':1,'max':365,'inputmode':'numeric'}),
        }
        help_texts = {
            'min_temperature': 'Me’yor mahsulot turiga qarab farq qiladi. Tasdiqlangan chegarani kiriting.',
            'max_temperature': 'Chegara belgilanmasa, tizim avtomatik me’yor bahosini bermaydi.',
            'max_storage_days': 'Bu faqat nazorat chegarasi, mahsulot xavfsizligi yoki yaroqlilik kafolati emas.',
            'check_interval_hours': 'Yangi o‘lchov kiritilmagan vaqt shu chegaradan oshsa, “qayd eskirgan” chiqadi.',
        }


class CameraEnvironmentReadingForm(forms.ModelForm):
    class Meta:
        model = CameraEnvironmentReading
        fields = ('measured_at','temperature','humidity','note')
        widgets = {
            'measured_at': forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'),
            'temperature': forms.NumberInput(attrs={'step':'0.01','min':-80,'max':80,'inputmode':'decimal','placeholder':'masalan: 1.5'}),
            'humidity': forms.NumberInput(attrs={'step':'0.01','min':0,'max':100,'inputmode':'decimal','placeholder':'masalan: 88'}),
            'note': forms.Textarea(attrs={'rows':2,'placeholder':'O‘lchov yoki tekshiruv haqida izoh'}),
        }
        help_texts={'measured_at':'O‘lchangan haqiqiy sana va vaqt. Qo‘lda kiritilgan yozuv o‘zgartirilmaydi.'}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not self.is_bound:
            self.initial.setdefault('measured_at',timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M'))

    def clean_measured_at(self):
        value=self.cleaned_data['measured_at']
        now=timezone.now()
        if value > now + timedelta(minutes=5):
            raise forms.ValidationError('Kelajakdagi o‘lchov vaqtini yozib bo‘lmaydi.')
        if value < now - timedelta(days=90):
            raise forms.ValidationError('90 kundan eski o‘lchovni kiritish mumkin emas.')
        return value
