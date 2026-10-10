"""Mobile-first setup forms; only platform superadmins may submit these views."""
from decimal import Decimal
from django import forms
from django.core.validators import MinValueValidator
from .models import Organization, Facility, Camera


class OrganizationSetupForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'code', 'camera_limit']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Masalan, Oltiariq Agro Star MCHJ', 'autocomplete': 'organization'}),
            'code': forms.TextInput(attrs={'placeholder': 'oltiariq-agro-star', 'autocapitalize': 'none'}),
            'camera_limit': forms.NumberInput(attrs={'inputmode': 'numeric', 'min': 1}),
        }
        help_texts = {
            'code': 'Takrorlanmaydigan qisqa kod. Masalan, oltiariq-agro-star.',
            'camera_limit': 'Tashkilotdagi jami kameralar limiti. Barcha filiallar hisoblanadi.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['camera_limit'].min_value = 1
        self.fields['camera_limit'].widget.attrs['min'] = '1'

    def clean_name(self):
        value = self.cleaned_data['name'].strip()
        if not value:
            raise forms.ValidationError('Tashkilot nomini kiriting.')
        return value


class FacilitySetupForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['organization', 'name', 'code', 'region', 'district', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Masalan, Oltiariq asosiy ombor'}),
            'code': forms.TextInput(attrs={'placeholder': 'oltiariq-1', 'autocapitalize': 'none'}),
            'region': forms.TextInput(attrs={'placeholder': 'Farg‘ona viloyati'}),
            'district': forms.TextInput(attrs={'placeholder': 'Oltiariq tumani'}),
            'address': forms.TextInput(attrs={'placeholder': 'Ko‘cha va uy raqami'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organization'].queryset = Organization.objects.filter(is_active=True).order_by('name')


class CameraSetupForm(forms.Form):
    facility = forms.ModelChoiceField(
        label='Tashkilot / filial',
        queryset=Facility.objects.none(), empty_label='Filialni tanlang',
    )
    number = forms.IntegerField(
        label='Kamera raqami', min_value=1,
        widget=forms.NumberInput(attrs={'inputmode': 'numeric', 'min': 1, 'placeholder': '1'})
    )
    name = forms.CharField(
        label='Kamera nomi (ixtiyoriy)', max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Masalan, uzum saqlash kamerasi'})
    )
    capacity_kg = forms.DecimalField(
        label='Sig‘imi, kilogramm', max_digits=12, decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'inputmode': 'decimal', 'placeholder': '23000'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['facility'].queryset = (
            Facility.objects.select_related('organization')
            .filter(is_active=True, organization__is_active=True)
            .order_by('organization__name', 'name')
        )
