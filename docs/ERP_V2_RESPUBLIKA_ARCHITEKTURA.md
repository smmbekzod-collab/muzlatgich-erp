# MUZLATGICH ERP 2.0 — Respublika miqyosidagi platforma loyihasi

**Holati:** DRAFT / tahlil uchun. **Sana:** 2026-10-10. **Muhim:** ushbu fayl hech qanday ishlab turgan kodni, tarifni yoki bazani o'zgartirmaydi.

## 1. Maqsad va chegaralar
Platforma O'zbekiston bo'ylab mustaqil tashkilotlar va ularning filiallaridagi sovutkichli omborlarni boshqaradi. Bitta tashkilot bir nechta viloyat va filialda ishlashi mumkin. Har bir tashkilot ma'lumotlari boshqa tashkilotlardan server tomonida ajratiladi. Operatsion ERP va platforma obunasi hisob-kitobi qat'iy ajratiladi.

## 2. Amaldagi kod bo'yicha asos (51efc6a46cf3)
- `core.models`: Organization, Camera, Membership; superadmin tashkilot/kamera/xodim huquqlarini boshqaradi.
- `warehouse.models`: Customer, Tariff, Lot, Operation, Expense; partiya QR, qisman chiqim, ko'chirish, yo'qotish, to'lov, qarz va hisoblar bor.
- `warehouse.services`: `receive`, `act`, `quote`, `pending`, `totals`; sovutish hozir so'm/kg/kun, saqlama so'm/oy tarzida ishlaydi.
- `warehouse.views`: brauzer/PWA ish rejimi, CSV/XLSX hisobotlari.
- TT bo'yicha hali yo'q: Branch/Facility, kelish vaqti, yangi bosqichli tarif, harorat/namlik jurnali, IoT, mijoz kabineti, obuna, analitika/AI.
- `Lot.created_at` serverdagi yozuv vaqti, **faktik yuk kelgan soat** sifatida qabul qilinmasin.

## 3. Ma'lumotlar arxitekturasi (yangi obyektlar)
| Obyekt | Vazifasi | Muhim qoida |
|---|---|---|
| `Organization` (mavjud) | Yuridik mijoz tashkilot | Tenant chegarasi |
| `Facility` (yangi) | Filial / ombor manzili, viloyat, tuman, vaqt zonasi, faollik | `organization_id` majburiy |
| `Camera` (mavjud, kengaytiriladi) | Har bir filiallardagi kameralar, sig'im | `facility_id` majburiy bo'lishidan oldin ma'lumot ko'chiriladi |
| `Membership` (mavjud, kengaytiriladi) | Tashkilot + filial/kamera scope + aniq huquqlar | Superadmin vakolati o'zgarishsiz |
| `TariffPolicy` / `TariffBand` | Kunlik, oylik yoki bosqichli kilogramm narxi | Har bir tashkilotga xos; sana chegaralari aniq |
| `LotTariffSnapshot` | Partiya qabul qilingandagi tarifning o'zgarmas nusxasi | Keyingi tarif o'zgarishi eski yukni o'zgartirmaydi |
| `TemperatureReading` | Kamera harorati/namligi, vaqt, manba, xodim/datchik | Qo'lda va IoT manbalar bir xil sxemada |
| `QualityInspection` | Mahsulot holati va nuqson dalolatnomasi | Fotosuratlarga kirish tenant bo'yicha |
| `Alert` + `AlertDelivery` | Qoida, holat, yuborish/etkazish tarixi | SMS/Telegram xatolarini qayta urinish |
| `SubscriptionPlan` + `OrganizationSubscription` | ERP foydalanish paketi va to'lov muddati | Ombor xizmat haqi ledgeridan mustaqil |
| `EnergyReading` | Hisoblagich kWh, vaqt, kamera/filial | Elektr xarajati va kWh/kg farqlanadi |
| `InventoryAudit` | Real sanash va qoldiq tafovuti | Rozilik va reversni auditlash |

**Bosqichli migratsiya:**
1. `Facility` jadvalini yaratish. `Camera.facility` maydoni boshida nullable.
2. Har bir eski `Organization` uchun "Asosiy ombor" filialini yaratib, eski kameralarga biriktirish.
3. Barcha kameralar biriktirilganini test bilan tekshirish.
4. Faqat keyingi chiqarishda `facility`ni majburiy qilish. Migratsiyada mavjud Lot/Operation/Customer ma'lumotlarini o'chirmaslik.
5. Region/tuman standart klassifikatoriga ega bo'lish; erkin satrni identifikator o'rniga ishlatmaslik.

## 4. Huquqlar va tenant izolyatsiyasi
- Har bir DB qidiruvida `organization_id`, tegishli holatda `facility_id` va `camera_id` bo'yicha filtr majburiy.
- Filial bo'yicha vakolat serverda tekshiriladi, UI ni yashirishning o'zi yetarli emas.
- Platforma superadmini tashkilot, filial, kamera va huquqlarni boshqarishni davom ettiradi.
- Rahbar, tashkilot admini, filial boshqaruvchisi, omborchi, buxgalter, mijoz roliga alohida ruxsatlar.
- Mijozlar uchun kirish: hisob tasdiqlanishi + o'z mijoz yozuvlariga bog'lash + log + token muddati. QR kodi ommaviy avtorizatsiya kaliti bo'lmasin.
- Platforma umumiy ko'rsatkichlari uchun agregatsiya va shaxsiy ma'lumotlarga minimal kirish.

## 5. Tarif mexanizmi — DRAFT (aniqlashtirilmagan shartlar bor)
Uchta hisoblash turi alohida qoladi:
- `COOLING_DAILY`: `billable_kg * daily_rate * billable_days` (mavjud mantiq)
- `STORAGE_MONTHLY`: pro-rata yoki boshlangan oy to'liq (mavjud mantiq)
- `TIERED_TOTAL_PER_KG`: `dispatched_billable_kg * rate_for_total_days`; 250/300/400/450 so'm/kg yakuniy bir martalik narx **faqat taxminiy talqin**, biznes egasi tasdig'isiz default qilib kiritilmaydi.

**Ochiq biznes qoidalar:** 1–6 kun narxi; 7,10,15,25,30 chegara sanalari; 30 kundan keyin narx; kelish/chiqish kunini hisoblash; qisman chiqim; tabiiy yo'qotishda qaysi kg tariflanadi; yaxlitlash; chegirma/soliq.

Hisoblash natijasi Operation yozuviga o'zgarmas summada saqlanadi; oldingi operatsiyalar qayta hisoblanmaydi. O'zaro hisob: tasdiqlangan xizmat haqi + avvalgi qarz - oldindan to'lov. Qarzga chiqarish mavjud ruxsat bilan boshqariladi. Fiskal chek tashqi qonuniy fiskallashtirish integratsiyasi bo'lmaguncha chiqarilmaydi.

## 6. Qabul va harakatlar
- `Lot.received_at` — kelgan real sana/soat; `created_at` — tizimga yozish vaqti. Tizim vaqt zonasi `Asia/Tashkent`.
- `Lot` qoldiq miqdori tushuncha sifatida saqlanadi, kirim/chiqim audit yozuvlari asosida solishtiriladi.
- Kirim, chiqim, ko'chirish va reversal idempotent; serverda tranzaksiya va lock.
- QR kodi partiya uchun mavjud; keyingi bosqichda `HandlingUnit`/pallet QR; har yashikka alohida QR majburiy emas.
- Tabiiy kamayish, chirish, sinish, tafovut sabablari alohida audit qilinadi.

## 7. Monitoring/AI
- MVP: omborchi qo'lda kuniga ikki marta harorat/namlik kiritadi, kechikkan qaydlar ko'rsatiladi.
- IoT: authenticated ingest endpoint, datchik ID, timestamp, dedup, sensor offline alert; alohida bosqich.
- AI oldidan deterministik dashboard: kirim tonna, mahsulot/nav, qoldiq, kamera foizi, o'rtacha kun, tushum, kWh/kg.
- Prognoz: tarixiy ma'lumot yetarliligi + model xatoligi + confidence interval. Meva sifati bo'yicha natija laboratoriya tekshiruvini almashtirmaydi.
- Xabarlar uchun background worker/queue va outbox; request-response ichida bevosita uzun SMS/AI chaqiruvini bajarmaslik.

## 8. Platforma daromadi
- `SubscriptionPlan` va `SubscriptionInvoice` tashkilotning ERP foydalanish huquqini anglatadi.
- `Operation.charge` omborning mijozga ko'rsatgan xizmat haqi bo'lib, SaaS subscription daromadiga qo'shilmaydi.
- Tarif paketlari, kamera/filial/foydalanuvchi kvotasi va foydalanish muddati.
- Obuna tugashi uchun grace period/readonly rejim biznes qoidasi tasdiqlanmaguncha yoqilmaydi.

## 9. Test va ishga tushirish shartlari
- Ishlab turgan `main` va Railway `production` ga kelishilmasdan tegmaslik.
- Avval backup va uning alohida muhitda restore testi; keyin staging migration.
- Testlar: tenant A foydalanuvchi tenant B yukini va QRini ocha olmasligi; filial scope; bir vaqtdagi qisman chiqim; eski tarif/qarz o'zgarmasligi; bosqich chegaralari; manual temp; subscription va ombor ledgeri izolatsiyasi.
- Ruxsatlar bo'yicha security test va yuklama sinovi, qulay mobil QR testlari.
- Har bir pull requestda migration, backward compatibility, rollback/restore yo'riqnomasi.

## 10. Reja
**A:** Backup/restore testi + filiallarga migratsiya + scope + audit testlar.
**B:** Tarif sxemasi va qisman chiqim qoidalari + chek/hisobni aniq ajratish.
**C:** Harorat/namlik qo'lda qayd + bandlik dashboardi + sifat jurnali.
**D:** Mijoz kabineti + Telegram + bildirishnoma navbati.
**E:** Obuna/kvota, IoT va AI analitikasi, yuridik/compliance tekshiruvi, pilot.

**Hozirgi qaror:** faqat loyiha hujjati. Ochiq tarif qoidalari kelishilmasdan pul hisoblaydigan yangi kod yozilmaydi.
