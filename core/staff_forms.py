"""Secure mobile form for creating a staff login and a scoped organization membership."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Organization, Facility, Membership


class StaffSetupForm(forms.Form):
    organization = forms.ModelChoiceField(
        label='Tashkilot', queryset=Organization.objects.none(), empty_label='Tashkilotni tanlang')
    username = forms.RegexField(
        label='Xodim logini', max_length=150, regex=r'^[\w.@+-]+$',
        error_messages={'invalid':'Login harflar, raqamlar yoki @ . + - _ belgilaridan iborat bo‘lsin.'},
        widget=forms.TextInput(attrs={
            'autocapitalize':'none', 'autocomplete':'username', 'placeholder':'masalan: omborchi01'}))
    first_name = forms.CharField(
        label='Ismi', max_length=150,
        widget=forms.TextInput(attrs={'autocomplete':'given-name','placeholder':'Xodim ismi'}))
    last_name = forms.CharField(
        label='Familiyasi', max_length=150, required=False,
        widget=forms.TextInput(attrs={'autocomplete':'family-name','placeholder':'Familiyasi'}))
    role = forms.ChoiceField(
        label='Lavozim / huquqlar to‘plami',
        choices=Membership._meta.get_field('role').choices,
        help_text='Lavozim tanlanganda ruxsatlar avtomatik beriladi. Kerak bo‘lsa, Super Admin orqali keyin tahrirlaysiz.')
    facility = forms.ModelChoiceField(
        label='Ruxsat berilgan filial (ixtiyoriy)',
        queryset=Facility.objects.none(), required=False,
        empty_label='Barcha filiallar',
        help_text='Filial tanlansa xodim faqat shu filialdagi barcha kameralarga kira oladi. Boshqa filiallar yopiq bo‘ladi.')
    password1 = forms.CharField(
        label='Xodim uchun parol',
        widget=forms.PasswordInput(attrs={'autocomplete':'new-password','placeholder':'Kamida 12 belgi'}))
    password2 = forms.CharField(
        label='Parolni tasdiqlash',
        widget=forms.PasswordInput(attrs={'autocomplete':'new-password','placeholder':'Parolni qayta kiriting'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organization'].queryset=Organization.objects.filter(is_active=True).order_by('name')
        self.fields['facility'].queryset=Facility.objects.filter(
            is_active=True,organization__is_active=True).select_related('organization').order_by(
            'organization__name','name')

    def clean_username(self):
        name=self.cleaned_data['username'].strip()
        if get_user_model().objects.filter(username__iexact=name).exists():
            raise forms.ValidationError('Bu login band. Boshqasini tanlang.')
        return name

    def clean(self):
        cleaned=super().clean()
        organization=cleaned.get('organization')
        facility=cleaned.get('facility')
        if organization and facility and facility.organization_id!=organization.pk:
            self.add_error('facility','Tanlangan filial boshqa tashkilotga tegishli.')
        password=cleaned.get('password1')
        repeated=cleaned.get('password2')
        if password and repeated and password != repeated:
            self.add_error('password2','Parollar bir xil emas.')
        if password and cleaned.get('username'):
            user=get_user_model()(username=cleaned['username'],
                    first_name=cleaned.get('first_name',''),last_name=cleaned.get('last_name',''))
            try:
                validate_password(password,user=user)
            except forms.ValidationError as error:
                self.add_error('password1',error)
        return cleaned
