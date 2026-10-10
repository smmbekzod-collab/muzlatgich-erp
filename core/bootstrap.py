"""Single-use staging first-admin setup. Disabled when no environment secret is set,
and forever disabled after the first superuser exists.
Never put the plaintext setup code in source or logs.
"""
import hashlib
import os
import secrets
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from warehouse.models import LoginThrottle


class InitialAdminForm(forms.Form):
    setup_code = forms.CharField(
        label='Bir martalik faollashtirish kodi', max_length=150,
        widget=forms.PasswordInput(attrs={'autocomplete': 'off', 'spellcheck':'false',
                                         'placeholder': 'Faollashtirish kodini kiriting'}))
    username = forms.RegexField(
        label='Yangi login', regex=r'^[\w.@+-]+$', max_length=150,
        error_messages={'invalid':'Login faqat harflar, raqamlar va @ . + - _ belgilaridan iborat bo‘lsin.'},
        widget=forms.TextInput(attrs={'autocapitalize':'none', 'autocomplete':'username',
                                      'placeholder':'Masalan: superadmin'}))
    password1 = forms.CharField(
        label='Yangi parol', widget=forms.PasswordInput(attrs={
            'autocomplete':'new-password','placeholder':'Kamida 12 ta belgi'}))
    password2 = forms.CharField(
        label='Parolni tasdiqlang', widget=forms.PasswordInput(attrs={
            'autocomplete':'new-password','placeholder':'Parolni qayta kiriting'}))

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if get_user_model()._default_manager.filter(username__iexact=username).exists():
            raise ValidationError('Bu login band. Boshqa login tanlang.')
        return username

    def clean(self):
        result = super().clean()
        password = result.get('password1')
        repeated = result.get('password2')
        if password and repeated and password != repeated:
            self.add_error('password2', 'Parollar bir xil emas.')
        if password and result.get('username'):
            temp = get_user_model()(username=result['username'])
            try:
                validate_password(password, user=temp)
            except ValidationError as error:
                self.add_error('password1', error)
        return result


def _setup_enabled():
    return (os.environ.get('ENABLE_STAGING_SETUP') == '1' and
            len(os.environ.get('STAGING_SETUP_CODE_SHA256', '')) == 64)


def _valid_code(code):
    expected = os.environ.get('STAGING_SETUP_CODE_SHA256', '')
    if not isinstance(code, str) or len(code) > 150 or not _setup_enabled():
        return False
    actual = hashlib.sha256(code.encode('utf-8')).hexdigest()
    return secrets.compare_digest(actual, expected)


def _too_many_attempts(request):
    raw = 'initial-setup|' + request.META.get('REMOTE_ADDR', '')
    key = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    now = timezone.now()
    cutoff = now - timedelta(minutes=15)
    entry = LoginThrottle.objects.filter(pk=key).first()
    if entry is None or entry.since < cutoff:
        LoginThrottle.objects.update_or_create(
            pk=key, defaults={'since': now, 'attempts': 0})
        return key, False
    return key, entry.attempts >= 8


def _record_failure(key):
    LoginThrottle.objects.filter(pk=key).update(attempts=F('attempts') + 1)


@never_cache
@sensitive_post_parameters('setup_code','password1','password2')
@require_http_methods(['GET', 'POST'])
def setup_superadmin(request):
    # Never allow this flow to run on production or after first admin.
    users = get_user_model()
    if not _setup_enabled() or users.objects.filter(is_superuser=True).exists():
        raise Http404('Yangi administratorni sozlash yopilgan.')

    if request.method == 'GET':
        return render(request, 'admin/initial_setup.html', {'form':InitialAdminForm()})

    key, blocked = _too_many_attempts(request)
    if blocked:
        response = HttpResponse('Urinishlar soni oshdi. 15 daqiqadan keyin qayta urinib ko‘ring.', status=429)
        response['Cache-Control'] = 'no-store'
        return response

    form = InitialAdminForm(request.POST)
    if not form.is_valid() or not _valid_code(request.POST.get('setup_code')):
        _record_failure(key)
        # Do not reveal if username or code matched; the code is single-use.
        form.add_error(None, 'Ma’lumotlarni tekshiring. Faollashtirish kodi, login va parol to‘g‘ri bo‘lishi kerak.')
        return render(request,'admin/initial_setup.html',{'form':form},status=200)

    with transaction.atomic():
        # Prevent two concurrent first-admin requests from both winning on PostgreSQL.
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [194272010])
        if users.objects.filter(is_superuser=True).exists():
            raise Http404('Administrator yaratilgan.')
        user = users.objects.create_superuser(username=form.cleaned_data['username'],
                                              password=form.cleaned_data['password1'])
        LoginThrottle.objects.filter(pk=key).delete()

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request,'Super Admin hisobingiz tayyor. Xush kelibsiz!')
    return redirect('/app/')
