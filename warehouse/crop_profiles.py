"""Advisory crop storage references — not automatic camera limits.

References:
  UC Davis grape: https://postharvest.ucdavis.edu/produce-facts-sheets/grape
  UC Davis carrot: https://postharvest.ucdavis.edu/ar/produce-facts-sheets/carrot
  FAO potatoes: https://www.fao.org/4/S1250E/S1250E0y.htm

Product names are free text, not verified commodity IDs. Avoid silently setting
alerts from an untrusted/incomplete classification. Admin sets per-camera limits.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CropReference:
    code: str
    name: str
    temperature: str
    humidity: str
    note: str
    source: str


REFERENCES = (
    CropReference(
        'grape','Uzum','−1…0°C','90–95%',
        'Stol uzumi; muzlashga va nav farqlariga ehtiyot bo‘ling.',
        'https://postharvest.ucdavis.edu/produce-facts-sheets/grape',
    ),
    CropReference(
        'carrot','Sabzi','0°C atrofida','98–100%',
        'Pishgan, barglari olingan sabzi uchun. Kondensat va etilen ta’sirini tekshiring. Bu namlikda sensor aniqligi juda muhim.',
        'https://postharvest.ucdavis.edu/ar/produce-facts-sheets/carrot',
    ),
    CropReference(
        'potato','Kartoshka (iste’mol uchun)','+4…+8°C','90–96%',
        'Jarohatlari bitgan kartoshka uchun. Qorong‘i, shamollatilgan xona; qovurish yoki urug‘lik maqsadiga moslanmaydi.',
        'https://www.fao.org/4/S1250E/S1250E0y.htm',
    ),
    CropReference(
        'potato_processing','Kartoshka (qayta ishlash uchun)','+7…+10°C','90–96%',
        'Qayta ishlash turi va navga qarab farq qiladi; chips uchun bundan yuqori harorat talab qilinishi mumkin.',
        'https://www.fao.org/4/S1250E/S1250E0y.htm',
    ),
    CropReference(
        'onion_dry','Piyoz (quruq)','0°C atrofida','65–70%',
        'To‘liq quritilgan, yetilgan bosh piyoz. Ko‘k piyoz yoki yangi yig‘ilgan nam piyoz uchun emas; shamollatish muhim.',
        'https://postharvest.ucdavis.edu/produce-facts-sheets/onions-dry',
    ),
)

# These are initial alert thresholds (not physical cooling controller setpoints).
# Where references specify a single nominal temperature of 0°C, allow +1°C
# observation tolerance; admins may adjust sensor-specific alert thresholds.
PRESET_LIMITS = {
    'grape': {'temperature':('-1.00','0.00'),'humidity':('90.00','95.00'),'commodity':'grape'},
    'carrot': {'temperature':('0.00','1.00'),'humidity':('98.00','100.00'),'commodity':'carrot'},
    'potato': {'temperature':('4.00','8.00'),'humidity':('90.00','96.00'),'commodity':'potato'},
    'potato_processing': {'temperature':('7.00','10.00'),'humidity':('90.00','96.00'),'commodity':'potato'},
    'onion_dry': {'temperature':('0.00','1.00'),'humidity':('65.00','70.00'),'commodity':'onion_dry'},
}
PROFILE_CHOICES = [('', 'Qo‘lda sozlash')] + [(p.code,p.name) for p in REFERENCES]

ALIASES = {
    'grape': ('uzum','kishmish','виноград','grape'),
    'carrot': ('sabzi','морковь','carrot'),
    'potato': ('kartoshka','картошка','картофель','potato'),
    'onion_dry': ('piyoz','лук','onion'),
}


def classify_product(raw):
    """Conservative word-boundary classification of an untrusted lot label."""
    if not isinstance(raw,str):
        return None
    cleaned=raw.casefold().replace('’',"'").replace('ʻ',"'").replace('‘',"'").replace('ʼ',"'").replace('`',"'")
    if any(term in cleaned for term in ("ko'k piyoz",'kok piyoz','yashil piyoz','barra piyoz','green onion', 'spring onion', 'зелёный лук', 'зеленый лук')):
        return None
    tokens=set(re.findall(r'[\w]+',cleaned,flags=re.UNICODE))
    found={kind for kind,aliases in ALIASES.items() if any(alias in tokens for alias in aliases)}
    return next(iter(found)) if len(found)==1 else None


def camera_crop_status(product_names):
    """Return safely displayable hint; never change tenant limits or storage."""
    products=[str(name) for name in product_names]
    types=[classify_product(name) for name in products]
    identified=sorted(set(kind for kind in types if kind))
    if not products:
        return {'state':'empty','message':'Kamerada ochiq partiya yo‘q. Keladigan mahsulotga qarab me’yorni qo‘lda belgilang.'}
    if any(kind is None for kind in types):
        return {'state':'unknown','message':'Ayrim mahsulot nomlari aniq tanilmadi. Kameraning me’yorlarini mutaxassis bilan tekshiring.'}
    if len(identified)>1:
        return {'state':'mixed','message':'Turli saqlash rejimli mahsulotlar bitta kamerada! Mosligini tekshiring; me’yorlar avtomatik o‘zgartirilmaydi.'}
    if len(identified)==1:
        return {'state':'single','message':'Kameradagi mahsulot tanildi. Quyidagi ma’lumotlar ma’lumotnoma; haqiqiy ogohlantirish me’yorini admin belgilaydi.','kind':identified[0]}
    return {'state':'unknown','message':'Mahsulot aniqlanmadi. Qo‘lda tekshirish talab etiladi.'}
