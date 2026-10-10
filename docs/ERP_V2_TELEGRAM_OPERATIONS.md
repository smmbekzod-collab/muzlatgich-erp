# ERP 2.0 TEST — Rahbar paneli va Telegram ogohlantirishlari

## Tayyor va sinovdan o'tgan
- \`/app/monitor/director/\`: moliyaviy ko'rish huquqi berilgan tashkilot/filial/kameralar bo'yicha so'nggi ko'rsatkichlar, faol hodisalar va Telegram holati. Platforma Super Admin barcha tashkilotlarni ko'ra oladi.
- \`/app/platform/telegram/\`: faqat Platforma Super Admini tashkilotga bir dona Telegram chat manzilini belgilaydi va yoqadi/o'chiradi.
- Kamera me'yoridan chiqish, o'lchov eskirishi va ixtiyoriy saqlash kuni chegarasi bo'yicha hodisalar alohida DBda saqlanadi. Hodisa hal bo'lmaguncha bir xil turdagi ogohlantirish takroran yaratilmaydi; vaziyat normallashsa yopiladi.
- Yuborish holatlari: \`disabled\`, \`pending\`, \`sending\`, \`sent\`, \`failed\`. 5 martagacha qayta urinishlar. Xatolar va qaydlar DBda qoladi.
- \`python manage.py process_monitor_alerts --limit=10000 --send-limit=50\`: yangi eskirgan qaydlarni aniqlaydi va Telegram outbox ni yuborishga urinadi.
- Railway TEST: \`monitoring-alerts-cron\` alohida xizmat, har **15 daqiqada** ishlashga rejalashtirilgan. Bu qo'shimcha Railway resurslaridan foydalanadi.
- Bot tokeni Github, DB, brauzer yoki ChatGPT suhbatiga yozilmaydi. API jo'natish chog'ida o'tadigan token Railway service o'zgaruvchisi orqali keladi.

## Haqiqiy Telegram ulanishi uchun QILINISHI KERAK
1. Telegram'da BotFather orqali aynan ushbu loyiha uchun alohida bot yarating.
2. Botni xabar olinadigan guruh yoki chatga qo'shing. Chatning raqamli ID sini aniqlang. **Guruh chatidagi barcha a'zolar xabarlarni ko'radi.** Xabarlar tashkilot/kamera nomlarini o'z ichiga oladi, mijoz shaxsiy ma'lumotlari yuborilmaydi.
3. Super Admin orqali \`/app/platform/telegram/\` sahifasida tashkilotni, chat ID sini tanlang va "Ogohlantirishlarni yoqish" ni belgilang.
4. Railway \`muzlatgich-erp-v2-staging\` loyihasidagi **monitoring-alerts-cron** xizmatining \`Variables\` bo'limiga \`TELEGRAM_BOT_TOKEN\` nomli maxfiy o'zgaruvchini qo'shing. Tokenni bu chatga yubormang.
5. Railway \`muzlatgich-erp-v2-web\` xizmatida xohlasangiz faqat \`TELEGRAM_BOT_CONFIGURED=1\` nazorat indikatorini yoqing. Bu tokenning o'zi emas, UI indikator; ulanishni sinamasdan tasdiqlamaydi.
6. Omborchi kamerada tashkiliy me'yordan tashqari **sinov o'lchovi** kiritsin. Hodisa \`pending\` bo'ladi. Keyingi cron ishga tushgach \`sent\` yoki \`failed\` holati chiqishini tekshiring.
7. Tokenni, chat ID ni va botni almashtirsangiz faqat tegishli tashkilotning manzilini o'zgartiring, boshqa tashkilotlarga tegmang.

## Xavfsizlik
- Telegram yo'nalishini faqat platforma egasi belgilaydi, tashkilot admini esa o'z kamerasi me'yorini o'zgartiradi; omborchi o'lchov kiritadi.
- Hodisa ko'rinishi \`access.cameras(user)\` bilan serverda cheklanadi. Telegram yo'nalishiga begona tashkilot chat ID si avtomatik topilmaydi: uni Super Admin kiritadi.
- Oddiy HTTPS \`sendMessage\` API, 8 soniyalik cheklov, xavfsiz xato izohlari; token javob/jurnalga yozilmaydi.
- Dastur bo'lmagan IoT/datchikdan **real vaqt** ma'lumoti olaman demaydi. Ogohlantirish faqat kiritilgan oxirgi qaydga asoslanadi. 15 daqiqalik cron tekshiruv oralig'i ham nol soniyalik tezkor kafolat emas.
- Cheklov: PostgreSQL bilan parallel queue-consumer ishga tushishi, Railway cron vaqtida xatolar, guruhga real yuborish va telefon UI sinovi amalda qabuldan o'tkazilishi kerak.
- Telegram HTTP 403 ko'pincha bot guruhga qo'shilmagan, chat ID xato yoki bot bloklanganidan dalolat beradi.
- Rasmiy fiskal chek yoki EHF mavzusiga bu modul ta'sir qilmaydi.

## Holat
Bu \`planning/national-saas-v2-20261010\` tarmog'i va mustaqil \`staging\` PostgreSQL bazasiga tegishli. Eski \`main\` va amaldagi \`muzlatgich-erp\` bazasi o'zgarmaydi. Draft PR #1 hali merge qilinmaydi.


## Uch mahal tashkilot bo‘yicha avtomatik hisobot (2026-10-10)
- **08:00**, **14:00** va **20:00** Toshkent vaqtida har bir faol va yoqilgan Telegram chat uchun alohida umumiy hisobot.
- Railway cron UTC jadvali: \`0 3,9,15 * * *\`. Xizmat nomi: \`telegram-3x-daily-digests\`, komandasi: \`python manage.py send_scheduled_digests\`. Railway cron bir necha daqiqa kechikishi mumkin.
- 08:00 hisobot oralig‘i — avvalgi kundagi 20:00 dan, 14:00 — bugungi 08:00 dan, 20:00 — bugungi 14:00 dan.
- Hisobot: tashkilot nomi, faol partiyalar, qolgan yashiklar va kg, band kameralar, oraliqdagi kirim va chiqim, oraliqda yozilgan to‘lovlar, mavjud yuk bo‘yicha qarz, avval hisoblangan kamera ijarasi qarzi, faol kuzatuv ogohlantirishlari.
- \`(organization, report_date, slot_hour)\` birikmasi DBda noyob; jadval qayta ishga tushganda shu davr uchun ikkinchi yozuv yaratmaydi. Telegram API xabarni qabul qilgandan so‘ng worker to‘xtab qolsa, kamdan-kam hollarda qayta urinish takroriy xabar yetkazishi mumkin.
- Cron worker qayta urinish navbati uchun eski \`monitoring-alerts-cron\` xizmatiga tegishli \`process_monitor_alerts\` komandasini ham ishlatadi; 15 daqiqalik xavfsizlik ogohlantirishlari o‘zgarmaydi.
- Xodim/mijoz ismlari Telegram xabarda yuborilmaydi. Tashkilotlar faqat \`organization_id\` bo‘yicha SQL filtrlangan; qarzlar alohida kompaniya bilan qo‘shilmaydi.
- Telegram chatbot bitta: tashkilotlar soni ko‘payishi uchun BotFather orqali qayta-qayta bot yaratish shart emas. Har tashkilotning o‘z guruh/chat ID si bor. **Bir faol chat ID ni ikkita tashkilotga bog‘lash taqiqlanadi**, shunda ma’lumotlar bir guruhga aralashmaydi.
- Agar Super Admin \`08:00, 14:00, 20:00 — umumiy hisobotlar\` tugmasini o‘chirsa, bu tashkilotning kunlik hisobotlari to‘xtaydi, lekin kamera ogohlantirishlari mustaqil ravishda ishlashi mumkin.
- Telegram yuborish tezligi cheklovi (odatda guruhga daqiqasiga 20 ta, ommaviy bot uchun taxminan soniyasiga 30 ta xabar) e’tiborga olingan; navbat qayta ishlanadi va yuborish cheklangan tezlikda bajariladi.
- Sinov uchun \`TEST — Agro Star Muzlatkich ERP\` tashkiloti yagona tasdiqlangan \`Muzlatgichtest\` guruhiga biriktirilgan. Bir martalik namuna xabari davriy jadvalda haqiqiy hisob deb qayd etilmaydi. Namuna yuborgan alohida Railway servisi ishlatilib bo‘lgach o‘chiriladi.
- Faqat TEST/STAGING tarmog‘ida. Telefon orqali haqiqiy foydalanish va backup/restore qabul testlari o‘tkazilmaguncha \`main\` ga merge qilinmaydi.

### Xabar yuborishni tekshirish
1. Super Admin: \`/app/platform/telegram/\` — tashkilotga tegishli chat ID hamda ikkita mustaqil bayroq (ogohlantirish, 3 mahal hisobot).
2. Railway: \`telegram-3x-daily-digests\` xizmatida cron \`0 3,9,15 * * *\` bo‘lishi kerak (Toshkent UTC+5).
3. Guruhga kirib xabarni haqiqatan ko‘ring; DBdagi \`sent\` Telegram API muvaffaqiyatini anglatadi, inson o‘qiganini emas.
4. Kelishilgan jadval va 15 daqiqalik ogohlantirishlar bir-biridan alohida ekanini tekshiring.
5. User chatda bot tokenini oshkor qilgan bo‘lsa, BotFather orqali tokenni yangilang va Railway’dagi \`monitoring-alerts-cron\` servisining maxfiy qiymatini almashtiring; \`telegram-3x-daily-digests\` secret ayni qiymatga referens orqali ulangan.


## TEST vaqtida vaqtinchalik pauza — Super Admin boshqaruvi
- \`/app/platform/telegram/\` sahifasida **08:00 / 14:00 / 20:00 hisobotlari** uchun \`Hisobotlarni o‘chirish\` / \`Hisobotlarni yoqish\` mavjud.
- Shu sahifada **Harorat va namlik ogohlantirishlari** alohida \`Ogohlantirishlarni o‘chirish\` / \`Ogohlantirishlarni yoqish\` tugmasi bilan boshqariladi. Bularni ikkalasini o‘chirish barcha Telegram jo‘natishlarini to‘xtatadi.
- Har bir tashkilot qatoridagi \`Hisobotni o‘chirish / yoqish\` tugmasi faqat shu tashkilotning uch mahal hisobotlarini boshqaradi; shu tashkilotning xavf ogohlantirishlariga ta’sir qilmaydi.
- Tugmalar faqat faol Super Admin uchun, barcha POST so‘rovlar CSRF bilan himoyalangan.
- Pauza vaqtida yangi davriy hisobot hosil qilinmaydi, mavjud navbatdagi hisobotlar to‘xtatiladi, bot API chaqiruvlari amalga oshirilmaydi. Oldin yuborilgan hisobotlar va ombor DB yozuvlari saqlanadi.
- Hisobotlar qayta yoqilganda **o‘tkazib yuborilgan vaqtlarning barcha hisobotlari birdan yuborilmaydi**; keyingi rejalashtirilgan 08/14/20 soatdan davom etadi.
- Kamera ogohlantirishlari qayta yoqilgach, hamon faol bo‘lgan muammolar keyingi monitor tekshiruvida qayd etilishi va yuborilishi mumkin.
- **Railway xarajati:** tugma cron ishini ma’lumot olish/yuborish bosqichida erta tugatadi, ammo Railway rejalashtirilgan instansiyani ishga tushirish uchun resurs ishlatishi mumkin. To‘liq nol-ijro uchun cron xizmatlarini Railway interfeysida alohida to‘xtatish yoki jadvalini o‘zgartirish zarur, lekin bu holda ilovadagi tugmaning o‘zi cronni qayta faollashtirmaydi. Eski ERP xizmatlari va PostgreSQL o‘chirilmaydi.
- 2026-10-10: TEST muhiti alohida himoyalangan bir martalik komanda bilan \`reports=OFF\`, \`alerts=OFF\` qilib pauzaga qo‘yildi. Demo tashkilot, o‘lchov, QR, ijara va qarz ma’lumotlari o‘zgartirilmaydi.
