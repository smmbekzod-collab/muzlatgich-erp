# Universal IoT Hub — bitta hududdagi 1–25 kamera, har bir tashkilotga mustaqil

**Holat:** faqat `feature/universal-iot-hub-25-camera-20261012` tarmog‘ida. Productionga merge/migratsiya/deploy qilinmaydi. Testdan o'tmasdan ishga tushirmang.

## 1. SaaS chegarasi
- Tashkilot A (Oltiariq): o‘z `Organization`, fizik `Facility`, 1–25 ta `Camera`, o‘z gateway kalitlari, o‘z datchiklari.
- Tashkilot B (boshqa manzil): alohida `Organization`, `Facility`, gateway, datchik va kalitlar.
- Har bir HTTP so‘rovi gateway UUID + faqat bir martalik berilgan maxfiy kalit orqali autentifikatsiya qilinadi; server sensorga `gateway_id` bilan bog‘langan kamerani o‘zi topadi. So‘rov tanadagi tashkilot ID ga ishonmaydi.
- 25 ta kamera maxsus global chegara emas; platforma admini Organization.camera_limit qiymatini har tashkilot uchun belgilaydi (mavjud default 10, kerak bo‘lsa 25 ga oshiriladi).
- Bir hududda ko‘p gateway bo‘lishi mumkin; bir datchik faqat bitta gateway va bitta kameraga doimiy biriktiriladi.

## 2. Tavsiya etilgan jismoniy tarmoq

**Byudjetli boshlanish:** 25 dona sanoat `RS485/Modbus RTU` harorat+namlik datchigi + **1 dona izolyatsiyalangan RS485 portli mahalliy edge gateway**; bitta umumiy trunk (ketma-ket shina), har sensorga 1–25 Modbus manzil. Shuningdek 24V manba (datchik pasportiga muvofiq), signal kabeli, klemmalar, himoya, UPS, Ethernet router/4G zaxira. Datchiklar *kamera ichida*, gateway/router/elektronika *iliq texnik xonada*.

**Yuqori uzluksizlik:** 25 ni 13 + 12 qilib ikki mustaqil RS485 magistral va **2 dona gateway** orqali bo‘ling (yoki 2 portli haqiqiy mustaqil edge controller). Bir gateway uzilsa, boshqasining 12–13 kamerasi ishlashda qoladi. Bu ikkita faol master **bitta RS485 shinada** ishlashi degani emas. Alohida port/liniyalar. Har hudud uchun qo‘shimcha sovuq zaxira gateway foydali.

```text
TASHKILOT A / BIR HUDUD / 25 KAMERA
 [K01]--[K02]-- ... --[K13]   120Ω oxiri     (RS485 A)
       |                               |
    Kamera ichida datchiklar     Gateway A [texnik xona]
                                        |
 [K14]--[K15]-- ... --[K25]   120Ω oxiri   (RS485 B)
       |                               |
    Kamera ichida datchiklar     Gateway B [texnik xona]
                                        |
                            Switch/router --> Ethernet
                                        |       4G backup, UPS
                                        v
                           HTTPS -> Railway ERP Cloud
                          -> TASHKILOT A ma'lumotlari

TASHKILOT B / BOSHQA HUDUD: o'z kabeli, gateway(lar)i,
o'z kaliti -> SHU bulutli ERP -> FAQAT tashkilot B kameralari.
```

**Montaj nazorati**:
- RS485 ekranlangan 120Ω nominal twisted-pair, D0/D1 + signal common (ishlab chiqaruvchi pinoutiga qarab); magistral daisy-chain, uzun yulduz yo‘q.
- Ikki uchda termination (nominal 120Ω; qurilma hujjatiga muvofiq), oraliq nuqtalarga qo‘shmang. Bias va yerga ulash sanoat montajchisi tomonidan hisoblanadi.
- Slave soni va kabel masofasi datchik transiveriga, baud rate va pasportiga bog‘liq; klassik RS485 32 unit-load cheklovini hisoblang. 25 sensor + 1 master bu hisobga yaqinlashadi; 13/12 ta segment bilan zaxira ko‘proq.
- Sovuq/kondensat muhitga mos IP daraja, ish harorati va RH talablari o‘rganilsin. Kondensat, yuvish, namlik probini to‘g‘ri joylashtirish muhim. Kabel kirishlarini germetik yoping; sovutkich izolyatsiyasini buzmaslik.
- Past kuchlanish datchik kabelini 220/380V quvvat kabelidan xavfsiz ajrating. Quvvat yo‘qolsa mahalliy edge logger ham o‘chishi mumkin; UPS.
- Ethernet kabel/router texnik xonada; Wi-Fi signalining kameraga o‘tishi SHART EMAS.
- Qurilmalar/marka ma’lum bo‘lgach Modbus registrlarining aniq manzili, signed/scaled format, parity, baud rate, RS485 pinout hujjat bilan tasdiqlanadi.

## 3. Integratsiya kontrakti

Gateway lokal dasturi (`RS485 Modbus poller`, `Wi-Fi`, `MQTT` yoki boshqa adapter) sensor qiymatini o‘qib, **bir xil xavfsiz HTTPS JSON** ga aylantiradi. Bulutga to‘g‘ridan-to‘g‘ri RS485/MQTT TCP port ochilmaydi.

ERP endpoint (TEST branchda): `POST /app/api/iot/v1/readings/`

So‘rov sarlavhalari:
```http
Content-Type: application/json
Authorization: Bearer <gateway-uuid>.<only-once-shown-secret>
```

Misol (FAKAT soxta test ma'lumotlar):
```json
{"readings":[
 {"device_code":"cam01","event_id":"siteA-cam01-20261012T110500Z",
  "measured_at":"2026-10-12T11:05:00+05:00",
  "temperature":"1.75","humidity":"86.20"},
 {"device_code":"cam02","event_id":"siteA-cam02-20261012T110500Z",
  "measured_at":"2026-10-12T11:05:00+05:00",
  "temperature":"1.20","humidity":"87.30"}
]}
```

Bir so‘rovda 1–50 datchik, 32KB dan oshmasin. Har bir datchik uchun `event_id` doimiy va noyob; internet qaytsa xuddi shu ID bilan qayta yuborish **yangi qayd yaratmaydi**. Server boshqa qiymat bilan ayni ID kelganda 409 rad etadi. 2 xonali aniqlik; −80..+80°C va 0..100% RH umumiy texnik chek, mahsulotning me’yorini tashkilot o‘zi belgilaydi. O‘lchovga vaqt zonasi shart, yuborish vaqti soatga moslashtirilsin.

`CameraEnvironmentReading(source='sensor', recorded_by=None)` ga avtomatik yoziladi; `IoTReceipt` auditda qaysi gateway/datchikdan kelganini saqlaydi. Amaldagi `reconcile_camera()` me’yorlar bo‘yicha hodisa yaratadi; mavjud Railway Telegram cron jarayoni boshqaradi. **Telegram bir lahzada emas**: davriy cron navbatiga ko‘ra kechikishi mumkin. Qurilma offline holati portalda oxirgi signaldan hisoblanadi. Avval kamida bir marta signal bergan datchik keyinchalik belgilangan muddatdan oshib jim qolsa, kamera bo‘yicha `sensor_offline` hodisasi hosil qilinib mavjud Telegram cron navbatiga tushadi. Hech qachon ulanmagan yangi qurilma uchun Telegram xavf xabari yaratilmaydi.

Offline yig‘ilgan o‘lchovlar **30 kungacha** server tomonidan qabul qilinadi (server va qurilmaning soati to‘g‘ri bo‘lsin). Lokal navbat 30 kundan uzoq uzilishlarda avtomatik o‘chirilmaydi; bunday eskirgan paketlar qo‘lda eksport/tekshirishni talab qiladi.

## 4. Foydalanuvchi bosqichlari
1. Tashkilotning `camera_limit` 25 bo‘lsin, `Facility` va 1–25 `Camera` reyestrga kiritilsin.
2. Tashkilot admini `/app/iot/` da o‘z `Facility` si uchun 1 yoki 2 gateway qo‘shadi.
3. Gateway maxfiy kaliti **faqat bir marta** chiqadi; faqat lokal gateway HTTPS konfiguratsiyasiga yoziladi.
4. Har bir sensorga `device_code` va, RS485 bo‘lsa, noyob Modbus slave ID belgilanadi; kamera bilan bog‘lanadi.
5. Har bir kamera uchun alohida harorat-namlik me’yori va nazorat kunlari o‘rnatiladi.
6. Gateway lokal adapteridan **soxta test o‘lchovi** yuboriladi; ERPda manba Sensor, o‘lchov tarixi, vaziyat ko‘riladi.
7. Real datchik modeli ma’lum bo‘lsa, adapter Modbus registrlarini o‘qishga moslanadi. Buni asbobsiz taxmin qilmang.

## 5. Ishlash, outage va xavfsizlik
- HTTPS majburiy; server cookie orqali API autentifikatsiya qilmaydi.
- Maxfiy token bazada faqat xesh ko‘rinishida, yangi kalit berilsa eskisi o‘chadi.
- Boshqa tashkilot datchiklari kalit bilan yuborilsa 400 rad etiladi.
- Gateway elektr/internet uzilishida lokal SQLite kabi barqaror navbatga o‘lchovlarni yig‘ishi va tiklanganda ayni `event_id` bilan qayta yuborishi KERAK; paketlarni tasdiqsiz o‘chirib yubormang.
- Bulut ishlamay qolgan davrda Telegram orqali vaqtli ogohlantirish kafolatlanmaydi. Sovutgichni himoya qiluvchi **mustaqil mahalliy sirena/relay** alohida zarur.
- Sensor kalibrovkasi, noto‘g‘ri qiymat, soat drift, kalit yangilash, tarmoq izolyatsiyasi va TLS tekshirilsin.
- Qabul: 25 sensors / 25 cameras, ikki tashkilot izolatsiyasi, online/offline, dublikat, noto‘g‘ri kalit, manzil to‘qnashuvi, xatodan so‘ng tiklash, PostgreSQL, sensor uzilishi va real Telegram sinovi.
- **No production**: ishchi bazaga migratsiya yo‘q, Railway stagingga ham avtomatik deploy yo‘q. Avval alohida sinov, keyin foydalanuvchi qarori.

## 6. Muhim chegaralar

`Universal IoT Hub v1` serverdagi gateway/reyestr, qabul API va nazoratga ulanishni taqdim etadi. Har xil Wi-Fi/Modbus/MQTT datchiklarni **avtomatik aniqlaydigan universal plug-and-play mexanizm EMAS**. Sanoat Modbus datchigi modeliga mos mahalliy polling adapteri va haqiqiy gateway qurilmasi kerak; moslamani xarid qilishdan avval ishlab chiqaruvchi register/protokol jadvali talab qilinadi.

Ishlab chiqish tarmog‘ining yagona maqsadi — productionni asrash va dasturiy tayanchni sinash.
