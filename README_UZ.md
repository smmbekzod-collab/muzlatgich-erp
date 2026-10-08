# MUZLATGICH ERP — FAQAT UMUMIY EXCEL HISOBOTI

## O'zgargan fayllar (atigi 3 ta)
- `warehouse/views.py` — mavjud `report()` funksiyasiga `export=xlsx` variant qo'shildi. Boshqa funksiyalar saqlandi.
- `warehouse/general_excel.py` — yangi, faqat o'qish rejimida Excel eksporti.
- `templates/warehouse/report.html` — tepadagi `Excel uchun CSV` tugmasi `Umumiy Excel (.xlsx)` ga almashtirildi.

## O'rnatish
ZIP ichidagi 3 faylni GitHub repositorydagi aynan shu yo'llarga joylashtiring. `warehouse/views.py` va `templates/warehouse/report.html` eskilarini almashtiring; `warehouse/general_excel.py` yangi fayl sifatida qo'shilsin. `Commit changes` qiling, Railway deploy yakunini kuting.

Bu patch **avvalgi mijoz bo'yicha chiroyli Excel patchi o'rnatilgan versiya** asosida tuzilgan. O'sha patchdan keyin `warehouse/views.py` yoki `report.html` boshqa tahrirlar olgan bo'lsa, butun faylni almashtirmang: farqlarni birlashtirish zarur.

`XlsxWriter` kutubxonasi oldingi mijoz hisoboti patchidagi `requirements.txt` orqali mavjud. Ma'lumotlar bazasida o'zgarish yoki migratsiya yo'q. Eski CSV eksporti `?export=csv` bilan mavjudligicha qoladi, biroq asosiy tugma yangi XLSX formatini yuklaydi.

**Kameralar hisoboti** sahifada tanlangan sana oralig'i bo'yicha; **Partiyalar va qarzlar** esa joriy holat bo'yicha, aynan avvalgi hisobotdagi mantiq saqlanadi. Foydalanuvchi faqat o'ziga ruxsat berilgan kameralarni ko'radi.
