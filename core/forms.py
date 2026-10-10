from django import forms
from .models import Membership, Camera, Facility
class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = '__all__'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        org = self.data.get('organization') if self.is_bound else self.instance.organization_id
        self.fields['cameras'].queryset = Camera.objects.filter(organization_id=org) if str(org).isdigit() else Camera.objects.none()
        self.fields['facilities'].queryset = Facility.objects.filter(organization_id=org) if str(org).isdigit() else Facility.objects.none()
        self.fields['facilities'].help_text = 'Barcha filiallar belgilanmagan bo‘lsa, faqat shu yerda tanlangan filiallar ko‘rinadi.'
        self.fields['cameras'].help_text = 'Faqat tanlangan tashkilot kameralari. Yangi ruxsatda avval tashkilotni tanlab saqlang, so‘ng kameralarni belgilang.'
    def clean(self):
        data = super().clean()
        org = data.get('organization')
        selected = data.get('cameras')
        selected_facilities = data.get('facilities')
        if org and selected_facilities is not None and selected_facilities.exclude(organization=org).exists():
            self.add_error('facilities', 'Boshqa tashkilot filialini tanlash mumkin emas.')
        if org and selected is not None and selected.exclude(organization=org).exists():
            self.add_error('cameras','Boshqa tashkilot kamerasini tanlash mumkin emas.')
        return data
