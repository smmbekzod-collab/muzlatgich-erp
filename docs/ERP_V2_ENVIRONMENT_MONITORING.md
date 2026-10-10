# ERP 2.0 — Harorat, namlik va saqlash muddati (TEST)

## Operatorning ish jarayoni
- **Super Admin** tashkilot, filial, kamera va xodimlarni sozlaydi.
- **Tashkilot administratori** (\`can_set_tariffs\`) kamerada tasdiqlangan minimum/maksimum harorat, namlik, o'lchov oralig'i va ixtiyoriy nazorat kunini belgilaydi.
- **Omborchi** (\`can_monitor_environment\`) kameradagi o'lchovni qo'lda kiritadi. Yangi admin/omborchi rol shablonlariga ushbu huquq avtomatik qo'shilgan. Eskilarida ruxsatni Super Admin alohida yoqishi kerak.
- Barcha huquqli foydalanuvchilar kuzatuvning so'nggi holati, muddat va tarixini ko'radi.
- Kamera tarixidan **oxirgi 30 kunlik CSV eksport** olinadi (5000 satrgacha, Excel formula kiritish xavfidan himoyalangan). Eski tashkilotlarga kirish taqiqlangan.

## Chegaralar, kunlar va ogohlantirishlar
- Harorat/namlik uchun **avtomatik tavsiya qilingan me'yor yo'q**. Me'yor faqat foydalanuvchi kiritganda baholanadi.
- Me'yordan chiqish, belgilangan soatdan eski o'lchov va nazorat kunidan oshgan yuk aniqlanadi.
- Yuk kunlari kirim sanasidan hisoblanadi (birinchi kun ham kiradi). Yopilgan yukning muddati chiqish sanasigacha hisoblanadi.
- Ogohlantirish mahsulot chiriganligi, yaroqsizligi yoki xavfsizligi haqida ekspertiza emas.
- O'lchovlar audit tarixida saqlanadi, tahrirlanmaydi. Yangi natija uchun yangi qayd qo'shiladi.

## Hozir qo'llab-quvvatlanmaydi
Haqiqiy IoT datchigi, avtomatik API, Telegram/SMS xabarnoma, 24/7 ogohlantirish, bulutli AI bashorat va real vaqt harorati hali ulanmagan. Ekran faqat **saqlangan oxirgi o'lchovni** ko'rsatadi.

## QA va reliz
GitHub Actions orqali makemigrations --check va regressiya sinovi. Mavjud Lot/Operation/tariflar o'zgarmaydi. Branch staging Railway bazasidan foydalanadi, asosiy ERP bazasiga tegilmaydi. Telefon bilan o'lchov kiritish va mobil QR jarayoni bo'yicha qo'l sinovi hali zarur.
