# Universal IoT Hub — Wi-Fi, MQTT va RS485 adapterlari (lokal gateway)

Bu hujjat `feature/universal-iot-hub-25-camera-20261012` sinov tarmog‘idagi dasturiy adapterlarga tegishli. **Asosiy ERP/Railway production o‘zgartirilmaydi.**

## Qamrov

| Ulanish | Lokal adapter qanday ishlaydi? | Shart |
|---|---|---|
| Wi-Fi / HTTP JSON | Lokal tarmoqdagi datchik HTTP(S) GET JSON natijasini o‘qiydi | Qurilmaning ochiq JSON API manzili va fieldlari |
| MQTT | TLS orqali brokerga ulanadi, har datchikning aniq topiciga obuna bo‘ladi | MQTT broker + vendor topic/payload spetsifikatsiyasi |
| RS485 / Modbus RTU | USB-RS485 port orqali 1–25 sensorga ketma-ket so‘rov jo‘natadi | Registr manzili, scaling, baud, parity, slave ID pasportda |
| LoRaWAN / GSM | Hozircha adapter tayyor emas; kelajakdagi kengaytirish | Tarmoq serveri yoki vendor API |

**Hech bir Wi-Fi datchik umumiy avtomatik plug-and-play deb va’da qilinmaydi.** Wi-Fi aloqa turi, API standartini bildirmaydi. Ba’zi qurilmalar faqat ishlab chiqaruvchi bulutiga yoki telefon ilovasiga ishlaydi. Unda API/gateway bo‘lmasa ushbu adapter mos kelmaydi.

## 25 kamerali fizik hudud

Ikki mustaqil RS485 segment (13+12) va ikki mahalliy edge gateway tavsiya qilinadi. Wi-Fi/MQTT sensorlar shu joydagi edge gatewayga LAN orqali ulanishi mumkin, yoki har bir gatewayda alohida adapter ishlaydi. Boshqa tashkilotning omborida **boshqa gateway kalitlari va boshqa mahalliy config** bo‘ladi.

Har bir `code` ERPda datchikka biriktirilgan `IoTDevice.code` bilan aynan mos bo‘lishi kerak. ERPda **har bir IoT datchik uchun transport turi alohida tanlanadi**: Wi-Fi / HTTP JSON, MQTT yoki RS485 / Modbus. Ko‘p RS485 datchikni qo‘lda bittalab kiritish shart emas: IoT Hub panelida **25 tagacha kamera uchun ommaviy biriktirish** bor. Gateway A uchun 13 ta, Gateway B uchun qolgan 12 ta kamerani tanlab, har birida Modbus manzilini 1 dan boshlash mumkin. Bir mini-PC aralash datchiklarni qabul qilsa, ERPda gateway transportini **Bir nechta transportli gateway (mixed)** qilib belgilang. RS485 datchikda `address` 1–247 shart; boshqa turdagi datchiklarda Modbus manzil kiritilmaydi. MQTT topiclar butun mahalliy configda yagona bo‘lsin. Modbus slave address 1–247 har bir RS485 segment uchun alohida.

## Lokal mini-PC / Raspberry Pi sozlash

1. Mahalliy qurilmada Python 3.12+ va repodagi `scripts` papkasini o‘rnating.
2. RS485/MQTT uchun ixtiyoriy qo‘shimcha bog‘liqliklar: `pip install -r requirements-iot-edge.txt`. **Bu paketlar Railway/Django requirements.txt ga qo‘shilmaydi.**
3. `scripts/iot_edge.example.json` ni mahalliy kompyuterda `iot_edge.json` nomi bilan nusxalang; har datchikning haqiqiy JSON fieldlari yoki Modbus 0-based registrlarini qo‘llanmasiga qarab sozlang. **Misoldagi registrlar haqiqiy qurilma spetsifikatsiyasi emas.**
4. Maxfiy ma’lumotlar OS muhitida saqlansin; `IOT_BEARER`, `IOT_MQTT_USER`, `IOT_MQTT_PASSWORD` va boshqa sensor tokenlari GitHubga kiritilmasin.
5. 5 daqiqalik timer bilan:

```bash
export IOT_QUEUE_DB="/var/lib/iot/queue.sqlite3"
export IOT_URL="https://YOUR-TEST-SERVER/app/api/iot/v1/readings/"
export IOT_BEARER="GATEWAY_UUID.ONE_TIME_SECRET"
# Wi-Fi JSON + RS485 bir martalik so‘rov (cron/systemd timer orqali):
python -m scripts.iot_edge_bridge --config iot_edge.json poll
# Oldindan tasdiqlanmagan o‘lchovlarni ERPga yuborish:
python -m scripts.iot_gateway_shipper flush
# MQTT — doimiy mustaqil systemd service, TLS sertifikati bilan:
python -m scripts.iot_edge_bridge --config iot_edge.json mqtt
```

**Eslatma:** `mqtt` tinglovchi jarayon faqat lokal SQLite navbatga yozadi. Ikkinchi alohida timer orqali `flush` yoqilishi zarur. Lokal SQLite fayl yozish huquqi bor, quvvatdan himoyalangan persistent diskda saqlansin.

## Qurilma javobini moslashtirish

Wi-Fi HTTP vendor JSON misoli (faqat SHABLON): `{"data":{"temp_c":1.4,"relative_humidity":83.5,"timestamp":"2026-10-12T14:05:00+05:00"}}`. `temperature_path: data.temp_c`, `humidity_path: data.relative_humidity`.

MQTT payload misoli: `{"temperature":1.4,"humidity":83.5,"measured_at":"2026-10-12T14:05:00+05:00"}`. MQTT uchun timestamp yo‘q payload rad etiladi; retained xabarlar e’tiborsiz qoldiriladi, aks holda eski datchik yangi ko‘rinib qolishi mumkin. Mijoz bilan TLS majburiy; bir topic bitta device.

Modbus: `temperature_register`, `humidity_register` **0-based**, `*_signed` va `*_scale` vendor pasportiga muvofiq. Masalan `0.1` scale qiymatni 10 ga bo‘ladi; noto‘g‘ri scaling noto‘g‘ri xavf signaliga sabab bo‘ladi. Registers 16 bit integer (float32/ikki registr ishlatiladigan modellar bu adapter bilan bevosita mos emas, alohida decoder kerak).

## Sifat va xavfsizlik mezonlari

- Internet uzilsa lokal navbat o‘chmaydi; HTTPS qayta urinadi. Event ID sensor bilan juftlikda noyob saqlanadi.
- Gateway va datchik aloqasi boshqa-boshqa. Datchikning `last_seen_at` qiymati asl o‘lchov vaqtiga asoslanadi, internet tiklangan eski paket uni yolg‘ondan Online qilmaydi.
- Lokaldagi HTTP faqat IP bilan va xususiy tarmoqda; HTTP redirect rad etiladi. Internetdagi qurilmalar bilan HTTPS ishlatilsin.
- MQTT broker TLS sertifikati tekshirilsin, shifrsiz MQTT ulanmaydi.
- Sensor noto‘g‘ri qiymat bersa adapter shu o‘lchovni tashlab, qolgan kameralarni yig‘ishda davom etadi. Uskunalar fizik kalibrovkasini tekshirish shart.
- Sovutgichlar uchun mustaqil mahalliy ogohlantirish rele/sirena tavsiya qilinadi; bulut yoki internetga qaram bo‘lmasin.

## Qabul sinovlari

1. 25 ta sensor simulyatsiyasi, bir xil `event_id` bo‘lsa ham har xil kameralar mustaqil saqlansin.
2. HTTP noto‘g‘ri URL, redirect, noto‘g‘ri JSON — xavfsiz rad.
3. MQTT topic boshqa bo‘lsa va retained xabar bo‘lsa — rad. Timestamp yo‘q bo‘lsa — rad.
4. Modbus signed16, scaling, no-response holati — xato qayta ishlansin.
5. Offline queue -> qayta yuborish -> serverdagi qayta yuborishni dublikat deb aniqlash.
6. Django 220+ regressiyalar va PostgreSQL testlari muvaffaqiyatli bo‘lsin.
7. Keyin **haqiqiy vendor model tanlangach** real apparat sinovi. Ko‘rsatilgan HTTP URL/Modbus registrlar FAKE namuna.

Production releasega hech narsa qo‘shilmaydi.

## 8. ERPdan gateway JSON shablonini yuklab olish

Tashkilot administratori IoT Hubda gateway qatoridan 'Konfiguratsiyani yuklab olish' tugmasini bosadi. Endpoint: /app/iot/gateway/<UUID>/edge-config.json. Faqat o‘z tashkilotining vakolatli administratori yuklay oladi. Begona tashkilot gateway eksportiga ruxsat yo‘q.

Eksportda datchik kodi, kamera raqami, ulanish turi va Modbus manzili bor; **Bearer token, MQTT paroli, sensor parollari berilmaydi**. Noma’lum registrlar null, URL/topic/path esa bo‘sh. Fayl vendor pasportidagi haqiqiy ma’lumotlar bilan to‘ldirilmaguncha ishlatishga tayyor EMAS. Maxfiy sozlamalar faqat mahalliy muhit o‘zgaruvchilarida bo‘lsin.

## 9. Konfiguratsiyani qurilmaga ulanmasdan tekshirish

ERPdan yuklangan JSON hali ishlaydigan sensor sozlamasi emas: temperature_register, humidity_register, scale va Wi-Fi API URL/path, MQTT topic va timestamp ishlab chiqaruvchi pasporti asosida to‘ldiriladi. Eksportda token/parol bo‘lmaydi.

~~~bash
# Qurilmaga ulanmasdan avval barcha sozlamalarni tekshirish:
python -m scripts.iot_edge_bridge --config iot-edge-local.json validate
# Tekshiruvdan keyin mahalliy Modbus/Wi-Fi o‘qish:
python -m scripts.iot_edge_bridge --config iot-edge-local.json poll
# Navbatni HTTPS orqali test ERPga yuborish:
python -m scripts.iot_gateway_shipper flush
~~~

Validate buyrug‘i internet/datchik bilan aloqa qilmaydi: noto‘g‘ri yoki bo‘sh registr, URL, MQTT TLS va field xaritalarini rad etadi. Bu versiya faqat ikkala qiymatni (harorat va namlik) beradigan sensorlarni qo‘llaydi.

**Ogohlantirish:** hatto rasmiy Modbus registrlari kiritilganda ham parallel termometr/namlik o‘lchagich bilan kalibrovka sinovi kerak. Dastur noto‘g‘ri scalingni har doim o‘zi aniqlay olmaydi. Mahalliy mustaqil sirena/rele tavsiya qilinadi.
