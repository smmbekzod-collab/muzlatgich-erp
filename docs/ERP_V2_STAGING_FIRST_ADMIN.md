# ERP 2.0 — STAGING: birinchi Super Admin

**Maqsad:** yangi va bo‘sh staging PostgreSQL bazasida birinchi administrator hisobini telefondan xavfsiz yaratish.

1. Railway’ning faqat `muzlatgich-erp-v2-staging` loyihasida quyidagi muhit o‘zgaruvchilarini o‘rnating:
   - `ENABLE_STAGING_SETUP=1`
   - `STAGING_SETUP_CODE_SHA256=<bir martalik uzun tasodifiy kodning SHA256 xeshi>`
2. Bitta platforma egasi `https://<staging-domain>/setup/` sahifasini ochib, asl faollashtirish kodini, yangi login va yangi parolni yozadi.
3. Parol kamida 12 belgidan iborat va Django kuchli parol tekshiruvidan o‘tishi kerak.
4. Yaratilgach, u avtomatik `/app/` sahifasiga kiradi va `/setup/` boshqa hammaga 404 qaytaradi.
5. `STAGING_SETUP_CODE_SHA256` va `ENABLE_STAGING_SETUP` o‘zgaruvchilarini Railway Variables’dan olib tashlash tavsiya qilinadi.
6. Login sahifasi bundan keyin `/admin/login/` bo‘ladi. Parolni parol menejerida saqlang.

**Xavfsizlik:** kod GitHub’da yo‘q; server SHA256 xeshini ushlaydi. Parol faqat brauzerdan HTTPS orqali yuboriladi; bu chatga tashlanmaydi. Login muvaffaqiyatli bo‘lguncha urinishlar 15 daqiqada 8 martagacha cheklangan. Endpoint faqat `ENABLE_STAGING_SETUP=1` bo‘lgan muhitda faol.

**Ehtiyot:** dasturdagi `SECRET_KEY` doimiy saqlansin; keyin o‘zgartirilsa mavjud sessiyalar va oldindan imzolangan tasdiqlar kuchini yo‘qotadi. Alohida staging bazasi asosiy ERP bazasiga ulanmasin. `main`ga bu sozlashni konfiguratsiyasiz ko‘chirish endpointni yoqmaydi.
