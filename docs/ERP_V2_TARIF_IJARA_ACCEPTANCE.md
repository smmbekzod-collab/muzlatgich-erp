# ERP 2.0 — tariflar va kamera ijarasi (TEST)

**Holat:** alohida GitHub tarmog‘i, asosiy `main` va Railway ishga tushirilmagan.

## Narx usullari
**1. Muddatga ko‘ra kilogramm**: 1–10 kun: 250 so‘m/kg; 11–15: 300; 16–25: 400; 26–30: 450; 31+ dastlab 450. Bular faqat boshlang‘ich qiymatlar; har bir tashkilot o‘z stavkalarini kiritadi. Yosh birinchi kunni ham o‘z ichiga oladi. **Bu har kungi hisob emas**: amaldagi kun bosqichiga mos narx *qisman yoki to‘liq chiqayotgan kg* ga bir martalik qo‘llanadi. Sof yoki brutto vazn tarifda tanlanadi. 31 kundan keyingi stavka sozlanadi.

**2. Butun kameraning oylik ijarasi**: kamera + ijarachi + boshlanish sanasi + oyiga so‘m. Oy — ijara boshlangan kundan keyingi kalendar-oy aylanishi, 30 kunlik doimiy sikl emas. Bitta kamera va boshlanayotgan oy uchun **bir dona** hisob yoziladi. Ko‘p partiya bo‘lsa ham ularning ijara xizmati 0 so‘m; haq kamera hisobi orqali yoziladi. Kamera band bo‘lsa yangi butun-kamera sharti tuzilmaydi. Bir vaqtda ikki kontrakt mumkin emas. Kontraktni yopish uchun barcha yuklar chiqarilgan bo‘lishi kerak.

## Administrator
- `can_set_tariffs` huquqli tashkilot administratori kilogramm narxlarini yangi versiya sifatida belgilaydi: oldingi tarif yangi kirim uchun faol bo‘lmaydi, avvalgi Lot snapshot va tarixdagi Operation.charge o‘zgarmaydi.
- Kamera ijarasidagi summani administrator kontrakt yaratishda belgilaydi; keyingi ijara oyidan yangi narx yaratishi mumkin. Eski CameraRentalInvoice.amount o‘zgarmaydi.
- `can_take_payment` huquqli xodim ijara hisobi to‘lovlarini bank/naqd/karta bilan alohida ledgerda qayd qiladi.
- Butun-kamera rejimi tanlanganda foydalanuvchi ijara shartini kiritgach nol-so‘mlik partiya tarifi avtomatik yaratiladi.
- Platforma Super Admin tashkilot va kameralarni boshqarish vakolatini saqlaydi.

## Chek va hisobot
Partiya QR orqali ochiladi; qisman chiqimda xizmati `quote()` bilan aniqlanadi; oldindan hisob ko‘riladi, tasdiq imzolangan 15 daqiqalik token bilan himoyalangan; tasdiqlangan Operation uchun ichki kvitansiya tayyorlanadi. Kvitansiyada yakuniy kun va stavka ko‘rsatiladi.

Kamera ijara hisob-varaqasi va to‘lov tarixi alohida. Umumiy hisobotda kamera ijarasidan hisoblangan summa va ijara to‘lovlari ajratilgan; Excelda shu ikki yangi sahifa va CSV bo‘limi mavjud. Bu hujjatlar **rasmiy EHF yoki fiskal chek emas**. EHF/online-kassa/SMS API keyingi alohida integratsiya.

## Qabul va xavfsizlik
- GitHub Actions: makemigrations --check, Django check, collectstatic, regression tests.
- Hozirgi sinovlar SQLite bilan; real PostgreSQL concurrency, DB backup/restore, staging migratsiya, telefonda kamera, bir nechta tashkilot yuklamasi keyin alohida tekshirilsin.
- Org A ning useri Org B narxi, ijara hisob-varaqasi, partiyasi yoki to‘lovini ko‘rmasligi kerak.
- Qisman chiqim, qayta bosish/idempotency, ijara davri va narx versiyasi, oldindan to‘lov, muddat chegaralari sinovdan o‘tkaziladi.
- 31+ uchun 450 default biznes taxmini: barcha tashkilotlarga majburiy narx emas, admin o‘zgartiradi.
- Oylik hisob davri kalendar oylik aylanish bilan hisoblanadi, doimiy 30 kun emas.
- Hozir yangi ijara oyi uchun hisobni foydalanuvchi tugma bilan chiqaradi; **avtomatik tungi cron hali yo‘q**.

## Railway’ga chiqarishdan oldin
1. POSTGRESQL ma’lumot bazasini zaxiralash + tiklashni sinash.
2. Staging muhit ochib yangi migratsiyalarni tatbiq etish.
3. Real QR skaner va mobil blankalar bo‘yicha qabul sinovi.
4. Mavjud Lot va Operation yozuvlarining ma’lumotlari yo‘qolmaganini solishtirish.
5. Django pull request testlari muvaffaqiyatli tugamaguncha `main` ga merge qilmaslik.
