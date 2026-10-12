# Agro Star — uzum/meva sovuq omborlari uchun IoT sensorlar (2026-10-12)

**STATUS:** tizimning GitHub sinov tarmog‘ida texnik tanlash qo‘llanmasi. Hali real datchik sotib olinmagan va ulangan emas. Production tegilmaydi.

## 1. Mahsulot sharoiti va kamera profillari

Manba: UC Davis Postharvest Center.

| Mahsulot | Tavsiya etilgan harorat | Nisbiy namlik | Manba |
|---|---|---|---|
| Uzum (stol uzumi) | -1°C…0°C | 90–95% | https://postharvest.ucdavis.edu/produce-facts-sheets/grape |
| Olma (Golden Delicious) | 0°C ±1°C | 90–95% | https://postharvest.ucdavis.edu/produce-facts-sheets/apple-golden-delicious |
| Anor | 5°C (2 oygacha); uzoq muddatda taxm. 7.2°C | 90–95% | https://postharvest.ucdavis.edu/ar/produce-facts-sheets/pomegranate |

**Muhim:** hamma 25 kameraga avtomatik 0°C o‘rnatmang; kamera rejasini mahsulot/naviga va saqlash muddatiga moslang. Bu ma’lumotlar *monitoring* uchun tavsiya, sovutgich kontrollerini ERP orqali avtomatik boshqarish buyruği emas.

## 2. O‘zbekistonda sotuvda ko‘rinayotgan RS485 sensorlar

| Model | Internet taklifidagi dona narxi | ±RH aniqlik | RH diapazon | IP | Izoh |
|---|---:|---:|---:|---|---|
| Relsib DVT-05.RS.З.K | 800 993 so‘m | ±3% | 0–95% | IP54 | Eng arzon, yuqori RH chegarasiga juda yaqin va kondensatga ehtiyot bo‘lish shart. |
| Dostupnaya Avtomatika TH-30-RS | 1 288 838 so‘m | ±5% (53–100% RHda) | 0–100% | IP65 | Kondensat xavfi uchun korpus himoyasi yuqoriroq; **90–95% RHda aniqligi sustroq**; pilot sinov shart. |
| OWEN PVT100 | Narxni sotuvchidan olish kerak | modelga qarab ±2.5% RH | variantni tekshiring | IP65 | Sovuq xonalarga ham mo‘ljallangan sanoat variant, almashtiriladigan zond/filtr, mahalliy diler. |

- Relsib Yandex Uzbekistan: https://market.yandex.uz/uz/card/datchik-temperatury-i-otnositelnoy-vlazhnosti-rs485-modbus-rtu-dvt-05-rs-z-k-dlya-kamer-sushki/4320961206
- Relsib rasmiy tavsifi: https://relsib.com/product/datchik-temperatury-i-otnositelnoj-vlazhnosti-dvt-05rszk
- TH-30-RS Yandex Uzbekistan: https://market.yandex.uz/card/th-30-rs-datchik-temperatury-i-vlazhnosti-vozdukha-kanalnyy-24v-s-vykhodom-rs485-modbus-rtu/4441927876
- TH-30-RS ishlab chiqaruvchi qo‘llanmasi: https://cdn.vseinstrumenti.ru/instruction/nomenclaturecontent/202401/32826730.pdf/12571313_manual.pdf
- OWEN PVT100 mahalliy sotuvchi: https://asu.uz/product/pvt100
- OWEN yuqori namlikda **kondensatsiyasiz** ishlash talabi: https://docs.owen.ru/product/pvt100/doc/rukovodstvo-po-ekspluatacii-pvt100/uslovia-ekspluatacii

Narxlar dinamik; sotuvchi 25 dona borligi, kafolat, boj/transport va chegirmalarni alohida tasdiqlashi kerak.

Faqat **25 dona sensorning** taxminiy qiymati: Relsib **20 024 825 so‘m**, TH-30-RS **32 220 950 so‘m**. **Bunga gateway, mini-PC, USB-RS485, quvvat bloklari, kabel, UPS, router/4G va montaj kirmaydi.**

## 3. Bir hududda 25 tagacha kamera

- 2 mustaqil segment tavsiya: K01-K13, K14-K25. Har segmentda bitta mahalliy Linux edge gateway yoki alohida RS485 portli boshqaruvchi.
- 25 dona RS485 harorat+namlik sensori (dastlab **1 ta sinov**, so‘ng partiya).
- 2 dona izolyatsiyalangan USB–RS485 adapter (agar Linux mini-PC ishlatilsa).
- 2 dona Linux mini-PC yoki Python kodini ishga tushira oladigan dasturlanadigan industrial gateway (faqat oddiy RS485–Ethernet konvertor yetmasligi mumkin).
- 12/24V DC quvvat tizimi **sensorga muvofiq**, alohida sug‘urta, kabel-terminator (RS485 shina bosh/oxiri), RJ45 Ethernet, router, 4G rezerv, UPS, himoyalangan sensor-montaj qutilari va germetik kabel kirishlari.
- Aloqa/UPS/elektronika muzlatkich ichida emas, texnik xonada. Sovuq kamera ichiga sensor o‘rnatiladi; suv va kondensat bevosita probga tushmasin.

**Namlik 90–95%:** 53–100% diapazonda ±5% RH aniqlikdagi TH-30 faqat umumiy kuzatuv va qo‘pol xavf ogohlantirishi uchun yetarli bo‘lishi mumkin; 90% va 95% ni qat'iy ajratuvchi aniqlik uchun ±2–3% yoki yaxshi kalibrlangan yuqoriroq sinf sensor zarur. IP65 **sensor elementining kondensatsiyaga chidamliligi kafolati emas**. Barcha kandidatlar ishlab chiqaruvchi ko‘rsatgan non-condensing cheklovlari bilan tekshirilsin.

## 4. TH-30-RS aniq Modbus profili — namuna kodi tayyor

Qo‘llanma 4-bet:
- RS485 Modbus RTU, zavod sozlamasi odatda **9600 8N1**, har datchikda yagona slave ID.
- **Holding** (funksiya 03) register **0** = namlik ×10 (0...1000 unsigned).
- **Holding** (funksiya 03) register **1** = harorat ×10 (signed INT16; masalan -5 => -0.5°C).
- Modbus slave ID sozlamasining alohida registeri 2000; bu registrni adapterimiz avtomatik **yozmaydi**, IDni montajchi vendor moslamasida sozlaydi.
- Fayl: `scripts/profiles/th30rs.modbus.example.json`.

Haqiqiy qurilma pasportidagi versiya yuqoridagi umumiy TH-30 qo‘llanmasiga mosligini tasdiqlash kerak. Aloqa parametrini sinovda faqat read-only o‘qish orqali tekshiring. `temperature_register=1`, `humidity_register=0`, `temperature_signed=true`, `scale=0.1`. Profilni mahalliy edge kompyuterda sinash, real uskunasiz simulyatsiya qilish mumkin.

## 5. Sotib olishdan oldingi qabul shartlari

1. Sotuvchidan aynan RS485 / Modbus RTU versiyasi, rasmiy pasport/register map, -1..+8°C hamda 90–95% RHdagi aniqlik, yuqori namlikda doimiy ishlash, kondensatsiya/shudring talabi, ta'mir va kafolatni yozma oling.
2. **1 dona sensor + sinov kabeli + 1 USB-RS485 adapter** bilan haqiqiy o‘lchov, tarmoq uzilishi va Telegram xabarlarini tajriba qiling.
3. Xonadagi va mahsulot qutisidagi haroratni alohida tekshiring: datchik **havo** holatini o‘lchaydi, mahsulot yadrosi haroratini emas.
4. Ishchi sovutgichning mustaqil termostat/alarm tizimini saqlang; IoT faqat nazorat va tarix.
5. Natija tasdiqlangandan keyin qolgan 24 dona va gatewaylarni buyurtma qiling, 25 ta kamerani ikki segmentda montaj qiling.

**Productionga hech narsa merge/deploy qilmang; real uskuna ulanmagan; bu xarid topshirig‘i emas, sinov reja.**
