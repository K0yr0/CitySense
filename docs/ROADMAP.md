# CityEcho Yol Haritası: Mobil + Web Admin + Sensör Simülasyonu (3 kişi)

Kullanıcılar uygulamayı **mobilden**, belediye **web'den** kullanır; otobüs sensörlerinin **simülasyonu** ayrı bir kişide. Üç kişi, her biri kendi bilgisayarında çalışıp aynı repoya push ediyor. Görevler **hiç çakışmayacak** şekilde dosya sahipliğiyle ayrıldı ve bu kural her commit'te makine tarafından kontrol ediliyor (`OWNERS` + git hook). Claude için kısa kurallar kökteki `CLAUDE.md` dosyasında.

| | Kişi A: 📱 Mobil | Kişi B: 🖥️ Web admin | Kişi C: 📡 Sensör simülasyonu ve veri |
|---|---|---|---|
| Ne yapar | Vatandaşın kullandığı uygulama | Belediyenin paneli; olaylar ve iş akışı | Sanal otobüslerin sensör verisini **üretir ve işler** |
| Görevler | M0–M7 | W0–W5 | S0–S5 |
| Dal | `mobile/...` | `admin/...` | `sensor/...` |
| Migration numaraları | 100–199 | 200–299 | 300–399 |

## Alınan kararlar

| Konu | Karar |
|---|---|
| Platform | Kullanıcı: **mobil uygulama** (React Native + Expo). Admin: **web** (Next.js) |
| Giriş öncesi güven puanı | Google girişinde **hesaba taşınır** |
| Admin yetkisi | **Tüm departmanları** görür |
| Sensör verisi | **Gerçek sensör / ESP32 yok, her şey simülasyon** (Kişi C). Simülatör, gerçek bir cihazın kullanacağı `/devices/stream` endpoint'ine aynı formatta veri gönderir. Web'deki `/ride` sayfası silinir |
| "Çevrende çukur var mı?" yarıçapı | **25 m**; yalnızca GPS isabeti ≤ 25 m iken sorulur |

## Proje yapısı

```
mobile/          → Kişi A   Kullanıcı uygulaması (Expo, iOS + Android)
web-admin/       → Kişi B   Belediye paneli (mevcut frontend/ buraya taşınır)
backend/sensor/  → Kişi C   Sensör hattı (algılama, harita eşleme, yol sağlığı)
scripts/simulate_buses.py → Kişi C   Sanal otobüs filosu (sensör simülatörü)
backend/ (geri kalanı) → A ve B, ama her dosyanın TEK sahibi var
```

## Çakışmayı önleyen 3 kural

1. **Her dosyanın tek sahibi var** (`OWNERS` dosyası). Okumak serbest, yazmak yalnızca sahibine ait. Başkasının dosyasına dokunan commit, bilgisayarda engellenir.
2. **Ortak dosyalar Gün 0'da bir kez hazırlanıp donduruluyor.**
3. **Kişiler birbirinin koduna değil, sözleşmesine dayanıyor.** Sözleşmeler aşağıdaki tabloda sabit.

---

## Gün 0: Ortak temel ✅ TAMAMLANDI (dondurulmuş)

Aşağıdakilerin hepsi yapıldı ve repoda. Ayrıca: Docker kurulumu (`docker-compose.yml`, `docker/`), harita dosyası `data/osm/segments_demo.geojson`, mobil iskeleti `mobile/` (Expo SDK 57). Sözleşmelerin ayrıntısı: `docs/ARCHITECTURE.md` §8.

| İş | Yapan |
|---|---|
| `backend/main.py`: tüm router'lar baştan kaydedilir (`users`, `responses`, `mobile`, `admin`, `devices`) | A |
| `backend/auth/`: Google token doğrulama, kendi oturum token'ımız, `current_user`, `require_admin` | A |
| `db/schema.sql` dondurulur; `db/migrations/` açılır (**A 100–199, B 200–299, C 300–399**); `scripts/init_db.py` migration'ları sırayla uygular | A |
| `requirements.txt` ve `.env.example`: tüm yeni bağımlılıklar ve değişkenler (google-auth, `GOOGLE_CLIENT_ID`, `ADMIN_EMAILS`, `DEVICE_KEYS`) | A |
| `mobile/` iskeleti (`npx create-expo-app`) | A |
| `frontend/` → `web-admin/` taşıması ve Vercel'de kök dizin güncellemesi | B |
| **S0:** Varşova harita segmentlerini veritabanına yüklemek (`scripts/load_osm.py --bbox demo`) | C |

**OpenAPI ve otomatik üretilen tipler git'e commit edilmez.** Her uygulama tiplerini çalışan backend'den kendi klasörüne üretir.

---

## Dosya sahipliği

| Alan | 📱 **Kişi A** | 🖥️ **Kişi B** | 📡 **Kişi C** |
|---|---|---|---|
| Uygulama | `mobile/**` | `web-admin/**` (şimdilik `frontend/**`) | — |
| Backend API | `auth/`, `api/users.py`, `api/responses.py`, `api/reports.py`, `api/mobile.py` | `api/admin.py`, `api/incidents.py`, `api/serializers.py`, `api/stats.py`, `api/vehicles.py`, `api/segments.py` (gösterim) | `api/devices.py` (yeni), `api/rides.py` |
| Backend mantığı | `fusion/trust.py`, `triage/**` | `fusion/incidents.py`, `verify.py`, `confidence.py`, `score.py`, `routing.py` | `sensor/**` (ingest, detect, lights, mapmatch, track_score, pipeline) |
| Veritabanı | `migrations/1xx_*` (users, favorite_routes, güven taşıma) | `migrations/2xx_*` (`work_status`) | `migrations/3xx_*` (devices, yol sağlığı zaman ağırlığı), `db/functions.sql` (`nearest_segment`, `recompute_segment_health`) |
| Scriptler | `gen_complaints.py`, `eval_triage.py` | `seed_demo.py` | `simulate_buses.py` (yeni), `synth_ride.py`, `replay_ride.py`, `load_osm.py` |
| Testler | `test_auth.py`, `test_mobile_*.py`, `test_triage_*.py`, `test_confidence_trust.py` | `test_admin_*.py`, `test_fusion.py`, `test_api.py` | `test_devices.py`, `test_sensor_*.py`, `test_db.py`, `test_load_osm.py` |
| Veri | `data/complaints_synth.json` | `data/demo/ztm_snapshot.json` | `data/demo/*.csv`, `data/osm/`, simülatörün ground truth dosyaları |

**Okuma her zaman serbest.** Örneğin A'nın `api/mobile.py` dosyası `incidents` ve `segments` tablolarını okuyabilir; `incidents`'e yalnızca B'nin, `segments.health`'e yalnızca C'nin kodu yazar.

**Ortak (SHARED) dosyalar** (`OWNERS` içinde işaretli): `backend/main.py`, `db/schema.sql`, `backend/config.py`, `backend/models.py`, `backend/db.py`, `requirements*.txt`, `.env.example`, `scripts/init_db.py`, `CLAUDE.md`, `docs/**`, `OWNERS`. Değişiklik süreci aşağıdaki "Git iş akışı" bölümünde.

Tam ve kesin liste `OWNERS` dosyasıdır; bu tablo özetidir. İkisi çelişirse `OWNERS` geçerlidir.

## Sözleşmeler (kişiler arasında, isimleri sabit)

| Veren → kullanan | Sözleşme | Ne için |
|---|---|---|
| A → B | `require_admin` (FastAPI bağımlılığı) | Admin endpoint'lerini korumak |
| A → B | `trust.settle(conn, incident_id, real=True)` (zaten var) | "Yapıldı" düğmesine basılınca güven puanlarını kapatmak |
| B → A | `incidents.work_status` sütunu (`todo` / `in_progress` / `done`) | Mobil, `done` olaylarda 25 m sorusunu durdurur |
| B → A | `incidents.confidence`, `incidents.status` sütunları | Mobildeki kısa olay görünümü |
| B → C | `fusion.incidents.ingest_evidence(conn, evidence_ids)` ve `verify.check_ride_verifications(conn, ride_id)` (zaten var) | C'nin sensör kanıtını olaylara bağlamak; geçişleri doğrulama olarak saymak |
| C → B ve A | `segments.health`, `segments.health_rides` sütunları (+ S3'te tazelik sütunu) | B'nin canlı haritası, A'nın yol renkleri. Yalnızca C yazar |
| C → B | `/devices/stream` veri formatı (`docs/ARCHITECTURE.md`'ye yazılır) | Simülatör, gerçek bir cihaz gibi bu formatta gönderir |

Sözleşme değişikliği gerekirse: grupta duyurulur, ilgili kişiler onaylar, değişiklik ayrı bir SHARED commit'iyle `docs/`'a yazılır.

---

## 📱 Kişi A: Mobil görevleri

| # | Görev | Ayrıntı |
|---|---|---|
| M0 | Kurulum | Expo iskeleti, backend'e bağlantı, demo modu |
| M1 | Harita | **Anlık konum** butonu (isabet halkasıyla); olaylar ve yol sağlığı **yalnızca renk** (iyi / orta / kötü / ölçülmedi) |
| M2 | Giriş | Google ile tek dokunuş; cihazdaki güven puanı hesaba **taşınır**; bildirmek ve cevaplamak için giriş şart, haritaya bakmak serbest |
| M3 | Sorun bildirme | Metin, kamera/fotoğraf, konum; sonrasında kısa durum ("23 kişi daha bildirdi", "belediye ilgileniyor", "yapıldı") |
| M4 | 25 m sorusu | "25 m çevrende çukur görüyor musun? Evet / Hayır". Yerel GPS, isabet ≤ 25 m, olay başına bir kez, `work_status = done` ise sorulmaz, cevaplar güvene göre ağırlıklı |
| M5 | Favori rotalar | Başlangıç/bitiş ya da otobüs/tramvay hattı; rota boyunca yol kalitesi renk olarak, "ileride kötü yol" uyarısı |
| M6 | Kısa olay görünümü | Tür, adres, güven etiketi, belediyenin iş durumu. **Sensör verisi, zaman çizelgesi ve olgular yok** |
| M7 | Bildirimler (opsiyonel) | "Bildirdiğin çukur onarıldı", "rotanda yeni sorun" |

## 🖥️ Kişi B: Web admin görevleri

| # | Görev | Ayrıntı |
|---|---|---|
| W0 | Taşıma | `frontend/` → `web-admin/`; kullanıcı sayfalarını (`/report`, `/ride`, vatandaş EVET/HAYIR) sil; tüm site admin girişi ister; ana sayfadaki üst üste binen görselleri düzelt |
| W1 | Olay kuyruğu | Departman, güven durumu ve iş durumu filtreleri; önceliğe göre sıralı; tüm departmanlar |
| W2 | Tam olay detayı | Sensör sinyal grafiği, **kanıt zaman çizelgesi**, **olgular**, güven dökümü, tüm raporlar ve fotoğraflar, vatandaş cevapları |
| W3 | İş akışı | **Yapılmadı → devam ediyor → yapıldı**, kim ve ne zaman değiştirdi. Güven durumundan ayrı alan. **Yapıldı** → `trust.settle` çağrılır, soru durur |
| W4 | Canlı harita (gösterim) | C'nin yazdığı `segments.health` ve tazelik bilgisini gösterir; canlı otobüs/tramvay konumları (Varşova API'si zaten çalışıyor) |
| W5 | İstatistikler | Rapor → olay → doğrulandı → yapıldı, ortalama onarım süresi, departman yükü |

## 📡 Kişi C: Sensör simülasyonu ve veri görevleri

Gerçek donanım yok; bütün sensör verisi simülasyondan gelir. Simülasyon, gerçek cihaz varmış gibi aynı endpoint'i ve aynı formatı kullanır.

| # | Görev | Ayrıntı |
|---|---|---|
| S0 | Harita segmentleri | Varşova yol ve ray ağını veritabanına yüklemek (`scripts/load_osm.py --bbox demo`). Overpass sunucusu yavaş, terminalden çalıştırılmalı. Herkesin ihtiyacı olduğu için **ilk iş** |
| S1 | Cihaz API'si | Sanal otobüs başına cihaz anahtarı, korumalı `/devices/stream`; gelen veriyi mevcut sensör hattına (`sensor/pipeline.py`) ve B'nin `ingest_evidence` fonksiyonuna bağlar. Veri formatı `docs/ARCHITECTURE.md`'ye yazılır |
| S2 | **Sensör simülatörü** | `scripts/simulate_buses.py`: gerçek güzergahlar boyunca (OSM segmentleri; isteğe bağlı canlı ZTM konumları) birçok sanal otobüs ve tramvay sürer. `synth_ride.py` mantığıyla ivme, GPS ve ışık verisi üretir; sabit, bilinen noktalara çukur, ray kusuru ve sönük lamba koyar; `/devices/stream`'e gönderir; koyduğu kusurların listesini (ground truth) saklar |
| S3 | Canlı yol sağlığı | Veri geldikçe `segments.health` yeniden hesaplanır, yeni ölçümler daha ağır basar (zaman ağırlığı); tazelik ve veri miktarı sütunları |
| S4 | Doğruluk ölçümü | Simülatörün ground truth'una karşı isabet / duyarlılık raporu (gürültü, hız ve telefon konumu değiştirilerek); sunum için "simülasyonda ölçüldü" diye sunulacak sayılar |
| S5 | Demo senaryoları | Sahnede tek komutla tetiklenen senaryolar: "yeni çukur oluştu → otobüsler buldu → şikayetten önce bulundu", "vatandaş bildirdi → sıradaki otobüs geçti → doğrulandı", "onarıldı → otobüs artık bir şey hissetmiyor". Tekrarlanabilir (sabit seed) |

---

## Sıra ve beklemeler

```
Gün 0:  A → backend temeli + giriş + mobile/ iskeleti   [SHARED commit'leri]
        B → frontend/ → web-admin/ taşıması
        C → S0 (harita segmentleri)
Sonra:  A → M0 → M1 → M2 → M3 → M4 → M5 → M6 (→ M7)
        B → W0 → W1 → W2 → W3 → W4 → W5
        C → S1 → S2 → S3 → S4 → S5
```

- **M4 ↔ W3:** "Yapıldıysa sorma" kısmı `work_status` sütunu gelene kadar pasif kalır, sütun gelince kendiliğinden çalışır. A beklemek zorunda değil.
- **M1/M5 ve W4 ↔ S2/S3:** Yol renkleri ve canlı harita, C'nin simülatörü çalışınca dolmaya başlar. O zamana kadar A ve B mevcut demo verisiyle çalışır, kimse beklemez.
- **Gün 0:** B ve C, A'nın SHARED commit'leri push edilene kadar yalnızca kendi klasörlerinde çalışır; bu sırada çakışma imkânsızdır.
- **S1 ↔ B:** C, B'nin mevcut `ingest_evidence` fonksiyonunu çağırır. Bu fonksiyon zaten var, B'yi beklemek gerekmez.

## Git iş akışı (herkes kendi bilgisayarında, doğrudan main'e push)

**Bir kez kurulum (her bilgisayarda):**
```bash
git clone https://github.com/K0yr0/cityecho.git && cd cityecho
git config core.hooksPath .githooks       # sahiplik kontrolü her commit'te çalışır
git config cityecho.role A                # kendi rolün: A, B ya da C
git config pull.rebase true
python3 scripts/check_owners.py --all     # "0 sahipsiz" demeli
```

**Her gün:**
1. `git pull`: işe başlamadan önce.
2. Yalnızca kendi dosyalarında çalış.
3. Testler: `.venv/bin/pytest` (B ayrıca `npm run build`). Geçmeden push yok.
4. `git commit`: hook, başkasının dosyasını ya da ortak dosyayı içeren commit'i engeller.
5. `git pull` + `.venv/bin/python scripts/init_db.py`: başkalarının migration'larını al.
6. `git push`: küçük ve sık.

**Neden çakışma çıkmaz:** iki kişi asla aynı dosyaya yazmadığı için `git pull --rebase` hiçbir zaman metin çakışması üretmez. Çakışma çıkarsa bu bir kural ihlalidir: dosyanın sahibine sorulur, kimse başkasının dosyasını kendisi "çözmez".

**Ortak (SHARED) dosya değişikliği:**
1. Grupta duyurulur; aynı anda yalnızca bir kişi yapar.
2. `git pull`, sonra yalnızca ortak dosyaları içeren ayrı bir commit: `CITYECHO_SHARED=1 git commit -m "..."`
3. Hemen push edilir; diğerleri `git pull` yapar.

**Yasaklar:** `git push --force`, `git commit --no-verify`, başkasının commit'ini geri almak, push edilmiş bir migration'ı düzenlemek, `.env` dosyasını commit etmek, commit mesajına Claude / Co-Authored-By satırı eklemek.

## Riskler

- **Simülasyon:** Bütün sensör verisi simülasyondan geliyor. Sunumda bunu açıkça söyleyin; doğruluk sayıları "simülasyonda ölçüldü" diye sunulur (S4).
- **Kişisel veri (RODO/GDPR):** Google girişi ve konum kullanımı kişisel veri demek. Yalnızca e-posta ve kimlik saklanır, konum geçmişi tutulmaz, gizlilik bildirimi eklenir.
- **Demo erişimi:** W0'dan sonra herkese açık Vercel sitesi admin girişi ister. Jüri için ya bir admin hesabı açılır ya da mobil uygulama Expo Go ile gösterilir.
- **Tramvay ve yol çukuru:** Tramvay yol çukurunu doğrulayamıyor; C'nin simüle otobüsleri yol çukurlarını doğrular.
- **main'e doğrudan push:** Her push Vercel'i yeniden yayınlar ve herkesi etkiler. Testleri çalıştırmadan push edilmez.
