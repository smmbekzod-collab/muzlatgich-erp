class PrivateResponses:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        if request.path.startswith(('/app/','/admin/')):
            response['Cache-Control']='private, no-store, max-age=0'
            response['Referrer-Policy']='same-origin'
        return response

class LoginProtection:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if request.path!='/admin/login/' or request.method!='POST':return self.get_response(request)
        import hashlib
        from datetime import timedelta
        from django.utils import timezone
        from django.http import HttpResponse
        from django.db.models import F
        from .models import LoginThrottle
        raw=request.POST.get('username','').casefold()+'|'+request.META.get('REMOTE_ADDR','')
        key=hashlib.sha256(raw.encode()).hexdigest();now=timezone.now();cut=now-timedelta(minutes=15)
        entry=LoginThrottle.objects.filter(pk=key,since__gt=cut).first()
        if entry and entry.attempts>=5:return HttpResponse('Kirish urinishlari ko‘p. 15 daqiqadan keyin qayta urinib ko‘ring.',status=429)
        response=self.get_response(request)
        if response.status_code==302 and request.user.is_authenticated:LoginThrottle.objects.filter(pk=key).delete()
        elif response.status_code==200:
            entry,created=LoginThrottle.objects.get_or_create(key=key,defaults={'since':now,'attempts':0})
            if entry.since<=cut:LoginThrottle.objects.filter(pk=key).update(since=now,attempts=0)
            LoginThrottle.objects.filter(pk=key).update(attempts=F('attempts')+1)
        return response
