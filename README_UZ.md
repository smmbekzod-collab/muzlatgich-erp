# MUZLATGICH ERP ERP — v0.2

Kompyuter va telefon brauzeri uchun ko‘p tashkilotli muzlatgich ombori ilovasi. Django + PostgreSQL. Asosiy ekran /app/, super admin /admin/.

## Nimalar ishlaydi
- Tashkilotlar, har bir tashkilotning kamera limiti, raqamlangan kameralar va brutto kg sig‘imi.
- Foydalanuvchini tashkilot va barcha yoki tanlangan kameralarga biriktirish. Har bir amal uchun alohida huquq.
- Mijoz, tarif, yuk kirimi, partiyaga yagona QR, chop etiladigan yorliq.
- QR skaner: telefon kamerasi yoki QR rasmini tanlash. QR login va kamera huquqini chetlab o‘tmaydi.
- Qisman/to‘liq chiqim: yashik, brutto, jami tara, netto, qoldiq; avval hisobni ko‘rish, keyin tasdiqlash.
- Yo‘qotish/buzilish, qoldiq partiyani boshqa kameraga ko‘chirish, saqlama hisobini yozish.
- To‘lov, avans, qarzdorlik, ichki kvitansiya; xarajatlar; kamera kesimida alohida saqlama/sovutish hisoboti va Excel ochadigan CSV eksport.
- Super admin eng oxirgi operatsiyani sabab bilan teskari yozuv orqali bekor qiladi. Asl hujjat saqlanadi. Kirimni bu usulda bekor qilish yopilgan.
- Telefon bosh ekraniga o‘rnatish uchun PWA manifest. Amal bajarish uchun internet kerak.

## Railway’da o‘rnatish
1. ZIP ichidagi fayllarni GitHub repository ildiziga yuklang: Dockerfile va manage.py ildizda tursin.
2. Railway’da repositorydan xizmat oching, shu loyihaga PostgreSQL qo‘shing. Dockerfile orqali build qilinadi.
3. Ilova Variables: DEBUG=0; SECRET_KEY uzun tasodifiy maxfiy kalit; DATABASE_URL PostgreSQL xizmatiga reference. Agar xizmat nomi Postgres bo‘lsa reference `${{Postgres.DATABASE_URL}}`.
4. Domen yarating. ALLOWED_HOSTS=your-domain.up.railway.app va CSRF_TRUSTED_ORIGINS=https://your-domain.up.railway.app. Bir necha domen vergul bilan. .env.example namuna, ilova .env faylini avtomatik o‘qimaydi.
5. Deploy qiling. start.sh migratsiyalarni bajaradi va Gunicornni PORT portida ishga tushiradi. /health/ sog‘lomlik tekshiruvi.
6. Railway CLI orqali tegishli loyiha va ilova xizmatiga ulang, `railway ssh` bilan ishlayotgan konteynerga kiring. Unda `python manage.py createsuperuser` bajaring; login va kuchli parolni o‘zingiz belgilang.
7. /admin/ ga kiring. Tashkilot, kamera, foydalanuvchi va Membership (administrator/ruxsat) yozuvlarini yarating. Xodimga Staff status bering; faqat bosh egaga Superuser status.
8. /app/ orqali avval mijoz va tarif yarating, keyin yuk kiriting. QR yorliqni chop eting. Telefonda HTTPS orqali skanerga kamera ruxsatini bering.
9. Dastlab bitta ilova replica ishlating. Bir nechta replica kerak bo‘lsa migratsiyani alohida pre-deploy bosqichiga ko‘chiring. PostgreSQL zaxira nusxa va tiklashni sozlang.

Avvalgi v0.1 ustiga yangilash: bazani zaxiralang, kodni almashtiring, deploy qiling. Mavjud migratsiyalarni yoki bazani o‘chirmang. Yangi xarajat huquqini kerakli xodimga alohida yoqing.

Railway manbalari (2026-10-08 tekshirildi):
https://docs.railway.com/guides/django
https://docs.railway.com/cli/ssh
https://docs.railway.com/databases/postgresql

## Dastlabki sozlash
Faqat super admin tashkilot/kamera yaratadi va limitni o‘zgartiradi. Faolsiz kamera ham limit ichida sanaladi; band kamera faolsizlanmaydi. Membershipda tashkilotni saqlab, keyin kameralarni tanlang. Barcha kameralar belgisi kelajakdagi kameralarni ham qamrab oladi. Lavozim nomi o‘zidan-o‘zi vakolat bermaydi.

Alohida huquqlar: kirim, chiqim/yo‘qotish, ko‘chirish, to‘lov, moliya, tarif, qarzga chiqarish va xarajat. Oddiy admin huquq yoki kamera yaratmaydi. Harakatlar bazada tranzaksiya ichida; takror bosilgan bir hujjat qayta yozilmaydi.

## Hisoblash qoidalari
Netto = brutto − jami tara. Tara maydoniga bitta yashik emas, shu operatsiyadagi barcha taraning jami kg qiymati kiritiladi. Qisman chiqimda haqiqiy tortilgan brutto va tara yoziladi. Oxirgi yashiklar bilan barcha qolgan og‘irlik ham chiqarilishi shart.

Sovutish: tanlangan netto yoki brutto kg × kunlik tarif × kun. Odatda chiqish kuni kiritilmaydi; tarifda uni qo‘shish mumkin. Har bir chiqarilgan qism kelgan sanasidan hisoblanadi. Qolgan yuk uchun kutilayotgan summa alohida ko‘rsatiladi, yozilgan qarz bilan aralashtirilmaydi.

Misol: 250 yashik, 2750 kg brutto, 250 kg tara = 2500 kg netto. 1-oktabr kirim, 6-oktabr 100 yashik/1100 brutto/100 tara chiqim, 300 so‘m netto tarifi: 1000 × 5 × 300 = 1 500 000 so‘m. Qoldiq 150 yashik, 1500 kg netto. 500 so‘m tarifda shu chiqim 2 500 000 so‘m.

Saqlama: oylik summa BUTUN PARTIYA uchun. 20 mln so‘m belgilansa, qisman chiqarishda avtomatik kamaymaydi. Ikki rejim: boshlangan oy uchun to‘liq yoki oy siklidagi haqiqiy kunlarga mutanosib. Sikl kirim sanasidan hisoblanadi, doim 30 kun deb olinmaydi. 1–7-oktabr saqlama yozuvi (7 kun/31): 20 000 000 × 7/31 = 4 516 129 so‘m. Avval yozilgan summa ayriladi, ikki marta undirilmaydi.

Har bir partiyaga hozir bitta xizmat tarifi tanlanadi: saqlama YOKI sovutish. Bitta partiyada ikkala xizmatni ketma-ket yoki bir vaqtning o‘zida hisoblash bu versiyaga kirmaydi. Tarifning keyingi o‘zgarishi oldingi partiyani qayta hisoblamaydi.

Pul butun so‘mga matematik yaxlitlanadi; og‘irlik 0.001 kg aniqlikda. Yo‘qotishda ketgan mahsulotning shu kungacha sovutish haqi yoziladi. Yashik yo‘qolmasa 0 yashik bilan og‘irlik yo‘qotish mumkin.

## Operatsion tartib
QR → partiya → Chiqarish → sana/yashik/brutto/tara → hisobni ko‘rish → to‘lov → tasdiqlash → kvitansiya. Qarzdorlik bo‘lsa, qarzga chiqarish huquqisiz chiqim bajarilmaydi. Oldindan tushgan avans qarzdan ayriladi. Kvitansiya ichki hujjat, fiskal chek yoki bank to‘lovi integratsiyasi emas.

Ko‘chirish butun qolgan partiyani ko‘chiradi; QR o‘zgarmaydi. Bir partiyani bir vaqtning o‘zida bir necha kameraga bo‘lish qo‘shilmagan. Xato chiqim/to‘lov/ko‘chirish uchun super admin eng oxirgi hujjatdan bekor qilishni tanlaydi. Tizim teskari hisob yozadi; real pul qaytarilishi alohida bajariladi.

Hisobotdagi sanalar yozilgan hisob/to‘lov/xarajatni filtrlaydi. Qoldiq, qarz va hali yozilmagan summa hozirgi holatdir. Tarixiy sana holatidagi inventarizatsiya emas. CSV Excelda ochiladi, alohida XLSX formulali kitob yaratilmaydi.

## Mahalliy ishga tushirish
Python 3.12 tavsiya etiladi.
```
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Linux/macOS: export DEBUG=1
# Windows PowerShell: $env:DEBUG='1'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
http://127.0.0.1:8000/app/ ni oching. SQLite faqat mahalliy ishlash/sinov uchun. Telefon kamerasi odatda HTTPS talab qiladi.

Test: `python manage.py test core warehouse` (DEBUG=1). TEKSHIRUV.md da haqiqiy tekshiruv doirasi yozilgan.

## Holat va chegaralar
Kod va deploy fayllari tayyor; sizning Railway akkauntingizga deploy qilinmagan. Standart login/parol yo‘q. Rasmlardan tarixiy ma’lumotlar avtomatik import qilinmagan. Amaliy ishga o‘tishdan oldin tashkilotingizning haqiqiy tarif shartlariga mosligini sinov partiyasida tekshiring.
Login: 15 daqiqada username/IP juftligiga 5 muvaffaqiyatsiz urinishdan keyin blok. 2FA va parolni email orqali tiklash yo‘q; super admin parolni almashtiradi. Audit oddiy ma’lumotlar bazasida, tashqi SQL o‘zgarishlarini aniqlovchi kriptografik audit emas.
