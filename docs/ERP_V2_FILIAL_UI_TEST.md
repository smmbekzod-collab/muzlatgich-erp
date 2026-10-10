# ERP 2.0 — Filiallar va qulay interfeys (TEST branch)

Bu kod faqat `planning/national-saas-v2-20261010` tarmog'ida. `main` va Railway production'da emas.

## Qo'shilganlar
- `Facility`: tashkilot ichidagi alohida filial/ombor, manzil va hudud.
- `Camera.facility`: tarixdagi kameralarning barcha ma'lumotini o'chirmasdan mavjud `Organization` uchun `Asosiy ombor` yaratiladi.
- `Membership.all_facilities` va `facilities`: filiallarga kirish serverda cheklanadi; eskilar default barcha filiallarga ruxsat bilan saqlanadi.
- Super Admin / admin panelida filial ro'yxati, kamera filiali.
- Bosh sahifada jami yashik, joriy partiyalar, kg, sig'im foizi; filial/kamera filtri.
- Telefon uchun katta tugmalar, bir ustunli kamera kartalari, jadvaldan mobil kartalar ko'rinishi va qulay kontrast.
- GitHub Actions uchun Django checks + migration checks + tests.

## Qabul sinovi
1. `DEBUG=1 python manage.py migrate`
2. `DEBUG=1 python manage.py check`
3. `DEBUG=1 python manage.py makemigrations --check --dry-run`
4. `DEBUG=1 python manage.py test`
5. Super Admin bir tashkilot uchun Oltiariq va Quva filialini ochib, ikki kamera biriktiradi.
6. Xodimga faqat Oltiariq filiali huquqi beriladi: Quva filiali / kamerasi ko'rinmasligi lozim.
7. Mavjud test yuklar QR/chiqim/to'lov va hisobotlari o'zgarishsiz qolganini tasdiqlash.
8. Android telefon, iPhone va desktopda QR, sahifa, chiqim tugmalari sinovi.

## Ehtiyot choralari
- Mavjud data o'chirilmaydi, lekin migrationsdan oldin DB backup + tiklash testi zarur.
- `Camera.facility` ustuni hozir nullable qoldirilgan: orqaga moslik va testlar uchun.
- Tashkilotga tegishli bo'lmagan filialni kameraga biriktirish rad etiladi.
- Tarixiy harakatlari bor kameraning filialini o'zgartirish rad etiladi.
- Bandlik **brutto kg / kamera sig'imi** bo'yicha, tarixiy to'lgan kun hisoblanmaydi.
- SaaS obuna, IoT, AI, bosqichli tarif hali ushbu kod patchiga kiritilmagan.
