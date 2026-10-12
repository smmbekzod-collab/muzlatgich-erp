# Avtomatik kamera mahsulot rejimlari — Agro Star Muzlatgich ERP

**Muhit:** faqat GitHub feature tarmog‘i. Production va bot sozlamalariga tegilmaydi.

## Foydalanish

1. Monitoring → kerakli kamera → **Saqlanadigan mahsulotni tanlash**.
2. Bittasini tanlang: **Uzum**, **Sabzi**, **Kartoshka (iste’mol)**, **Kartoshka (qayta ishlash)** yoki **Piyoz (quruq)**.
3. **Mahsulot rejimini avtomatik qo‘llash** tugmasini bosing.
4. Tizim shu kameraning harorat va namlik *ogohlantirish* chegaralarini yangilaydi. Boshqa kameralarga tegmaydi. Har bir tashkilot faqat o‘z kameralarini boshqaradi.
5. Kamera bo‘sh bo‘lsa, yangi mahsulot rejimi tanlanadi. Hali chiqimi tugamagan boshqa mahsulot partiyasi mavjud bo‘lsa, tizim noto‘g‘ri avtomatik almashtirishni **bloklaydi**.
6. Admin zarur bo‘lsa me’yorni qo‘lda o‘zgartira oladi. Qo‘lda tahrirlashda mahsulot presetiga bog‘liqlik bekor qilinadi, o‘lchovlar va partiyalar o‘zgarmaydi.
7. Sozlama o‘zgarishlari xronologiyasi va kim o‘zgartirgani saqlanadi.

## Tavsiya etilgan boshlang‘ich monitoring chegaralari

| Mahsulot | T min °C | T max °C | RH min % | RH max % |
|---|---:|---:|---:|---:|
| Uzum | -1 | 0 | 90 | 95 |
| Sabzi | 0 | 1 | 98 | 100 |
| Kartoshka, iste’mol uchun | 4 | 8 | 90 | 96 |
| Kartoshka, qayta ishlash uchun | 7 | 10 | 90 | 96 |
| Quruq bosh piyoz (cured) | 0 | 1 | 65 | 70 |

Uzum: https://postharvest.ucdavis.edu/produce-facts-sheets/grape
Sabzi: https://postharvest.ucdavis.edu/ar/produce-facts-sheets/carrot
Kartoshka: https://www.fao.org/4/S1250E/S1250E0y.htm
Quruq piyoz: https://postharvest.ucdavis.edu/produce-facts-sheets/onions-dry

Bu ko‘rsatkichlar dastlabki **monitoring/ogohlantirish** chegaralari. Masalan, sabzi va piyoz uchun 0°C *nominal* tavsiya qilingan; +1°C kuzatuv tolerance sifatida qabul qilingan, mahsulot navi va texnika aniqligiga ko‘ra administrator moslashtirishi lozim. Harorat va namlik ko‘rsatkichining sensor xatoligi hisobga olinsin, ayniqsa 98–100% RH sabzida. Sovuqxona fizik termostati va namlagichni bu ERP moduli avtomatik boshqarmaydi.

## Mahsulotlar aralashsa

Uzum, sabzi, kartoshka, piyozni bitta kamera rejimida avtomatik moslashtirib bo‘lmaydi:
- Sabzi: yuqori namlik.
- Piyoz: nisbatan quruq atmosfera, yaxshi ventilatsiya.
- Kartoshka: mahsulot yo‘nalishiga mos harorat.
- Uzum: muzlash nuqtasiga yaqin salqin saqlash.

Agar ochiq partiyalar turli toifada bo‘lsa yoki mahsulot nomi tanilmasa, **preset bloklanadi**. Tizim mavjud partiyani ko‘chirmaydi, chiqim qilmaydi yoki mahsulot nomini taxmin qilib xulosa chiqarmaydi. Kartoshkaning chips/kartoshka fri uchun variantini administrator aniq tanlaydi. **Ko‘k piyoz** quruq piyoz sifatida avtomatik tanilmaydi.

## Xavfsizlik va audit

- Faqat kamera uchun tarif/monitoring me’yorini o‘zgartirishga vakolatli administrator bu amalni bajara oladi.
- Boshqa tashkilotning kamerasiga POST yuborish 404/403.
- `CameraEnvironmentPolicy.profile_code` tanlangan mahsulot rejasini saqlaydi.
- `CameraEnvironmentProfileChange` jadvalida oldingi/yangi kod, to‘rtta limit, o‘zgartirgan xodim va vaqt saqlanadi.
- Mavjud `CameraEnvironmentReading`, QR, partiya, qarzdorlik, hisob-kitob va Telegram konfiguratsiyasiga o‘zgartirish kiritilmaydi.
- Kamera me’yorlari o‘zgargach, mavjud `reconcile_camera` xavf holatini qayta baholaydi va amaldagi Telegram jarayonlari keyin yuborishi mumkin. **Test serverida sinovsiz productionga chiqarmang**.
- Datchik/IoT gateway offline bo‘lsa, bu o‘zgarish uning ulanishini to‘g‘rilamaydi. Monitoringga haqiqiy o‘lchov kerak.

## Deploymentdan oldin

- Django migratsiyalar va regressiyalarni ajratilgan test DBda bajarish.
- 25 ta kamera, har birida mahsulot tanlash, mahsulot almashtirish, noto‘g‘ri ochiq partiya bilan blok, tenant huquqlari, qo‘lda override, audit testlarini o‘tkazish.
- Sabzi namligi va piyoz kondensati uchun real sensorni joyida tekshirish, sanoat montajchi bilan chegaralarni tasdiqlash.
- Ishlayotgan production ERP va Telegram botga tegmaslik. Deploy uchun alohida ruxsat va rollback rejasi.
