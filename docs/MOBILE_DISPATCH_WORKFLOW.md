# QR → Yuk chiqarish → Hisobni ko‘rish → Tasdiqlash → Kvitansiya

TEST branchdagi omborchi uchun telefon interfeysi. `main` va Railway productionga qo‘llanilmagan.

- QR scanner telefon va qo‘lda UUID/havola bilan ishlaydi.
- Partiya sahifasidan tezkor chiqim va navbatdagi QRga o'tish tugmalari.
- Chiqimda faqat **barcha qolgan yukni** bitta bosishda to‘ldirish; qisman chiqimda brutto/tara o‘lchanib qo‘lda yoziladi.
- Serverdagi `quote` xizmat va qarzni hisoblaydi; brauzer pulni o‘zi hisoblamaydi.
- Tasdiqlash faqat 15 daqiqalik server imzosi bilan; foydalanuvchi/partiya/kirim-chiqim/to‘lov maydonlari, balans va qoldiq mos bo‘lishi shart.
- Qoldiq/yangi to‘lov o‘zgarsa tasdiq rad etiladi; qayta hisob talab etiladi.
- Boshqa hujjat turlari va amaldagi tariflar o'zgarmaydi.
- Hujjatlar ichki kvitansiya: fiskal chek yoki rasmiy EHF emas.
- GitHub Actions regression testlari + telefon kamerasi va real PostgreSQL concurrency sinovi alohida talab qilinadi.
