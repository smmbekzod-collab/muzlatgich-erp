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
