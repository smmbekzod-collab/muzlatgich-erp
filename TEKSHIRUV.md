# Tekshiruv — 2026-10-08

62 avtomatik test muvaffaqiyatli o‘tdi (21.612 soniya). To‘liq natija test-report.txt ichida.

Tekshirildi: super admin va xodim vakolatlari; tashkilot/kamera izolatsiyasi; kamera limit/sig‘im; QR PNG va login nazorati; kirim; qisman/to‘liq chiqim va netto/brutto/tara; 300/500 so‘m; avans, qarzga chiqish huquqi; oy/yil chegarasi; saqlama takror hisoblanmasligi; yo‘qotish; ko‘chirish; idempotent qayta yuborish; CSRF; sahifalarning HTTP renderi; CSV; teskari operatsiya va login bloklash.

Django system check: muammo aniqlanmadi. Makemigrations --check --dry-run: o‘zgarish yo‘q. Collectstatic muvaffaqiyatli yakunlandi.

Test muhiti: Python, Django 5.2.18 va SQLite. PostgreSQLdagi parallel tranzaksiyalar alohida sinovdan o‘tkazilmagan. Brauzerning vizual testi, haqiqiy telefon kamera/QR skaneri va Docker image build bu muhitda bajarilmadi. Railway akkauntiga deploy qilinmagan. Shuning uchun bu natija serverdagi qabul sinovi o‘rnini bosmaydi.

Serverdagi qabul sinovi:
1. Ikki tashkilot va har birida kamera yarating; xodimning begona tashkilotga kira olmasligini tekshiring.
2. 250 yashik, brutto 2750, tara 250, netto 2500 bilan partiya kiriting.
3. QRni chop etib telefon orqali oching. 100 yashik/1100 brutto/100 tara chiqaring: 150 yashik/1500 netto qolsin.
4. Sana oralig‘i 5 kun va 300 so‘m netto tarifida 1 500 000 so‘m chiqishini tekshiring. To‘lov, kvitansiya va hisobotni solishtiring.
5. Alohida saqlama partiyasida 20 mln tarifni tashkilotingiz shartnomasi bilan solishtiring.
6. PostgreSQL zaxiradan tiklash va ikki xodimning bir vaqtdagi chiqimini staging muhitida tekshiring.
