# CityEcho: Claude için proje kuralları

Bu dosya her Claude Code oturumunda otomatik okunur. Ekipteki herkesin Claude'u aynı kuralları uygular.

**Proje:** Varşova akıllı şehir projesi. Otobüs ve tramvay sensörlerinden gelen veri (**tamamen simülasyon**) ile vatandaş şikayetleri aynı "kanıt"a dönüşür. Bir füzyon motoru bunları olaylara (incident) çevirir, güven motoru (confidence engine) durumunu belirler: aday (candidate) → muhtemel (likely) → doğrulandı (verified).

Ayrıntılar:
- Tam plan ve görev dağılımı: [docs/ROADMAP.md](docs/ROADMAP.md)
- Dosya sahipliği (makinenin uyguladığı): [OWNERS](OWNERS)
- Mimari ve API sözleşmeleri: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Neyin yapılıp test edildiği: [BUILD_REPORT.md](BUILD_REPORT.md)

## 1. Oturumun başında: kiminle çalışıyorsun?

Üç kişi, her biri **kendi bilgisayarında** çalışıp aynı repoya push ediyor. Görevler **kesinlikle çakışmamalı**.

| | Kişi A: 📱 Mobil (kullanıcı) | Kişi B: 🖥️ Web admin (belediye) | Kişi C: 📡 Sensör simülasyonu ve veri |
|---|---|---|---|
| Ana klasörler | `mobile/` (kod `mobile/src/`) | `web-admin/` | `backend/sensor/`, sensör scriptleri |
| Görev kodları | M0–M7 | W0–W5 | S0–S5 |
| Migration numaraları | 100–199 | 200–299 | 300–399 |

**İlk iş:** `git config --get cityecho.role` komutunu çalıştır.
- Boş çıkarsa: kullanıcıya A, B ya da C olduğunu sor ve kurulumu yap (bölüm 3).
- Doluysa: yalnızca o rolün dosyalarına yaz.

## 2. Kesin kurallar (ihlal etme)

1. **Her dosyanın tek sahibi var.** Sahiplik `OWNERS` dosyasında. Bir dosyaya yalnızca sahibi yazar; okumak serbest.
2. **Başkasının dosyasında değişiklik gerekiyorsa:** kodu kendin değiştirme. Kullanıcıya ne gerektiğini tam olarak yaz (dosya, fonksiyon, neden); o da sahibine iletsin.
3. **Ortak (SHARED) dosyalar dondurulmuş.** Bunlar `OWNERS` içinde `SHARED` diye işaretli: `backend/main.py`, `db/schema.sql`, `backend/config.py`, `backend/models.py`, `backend/db.py`, `requirements*.txt`, `.env.example`, `scripts/init_db.py`, `CLAUDE.md`, `docs/**`, `OWNERS`. Değiştirmek gerekirse:
   1. Önce grupta duyur, bir kişi yapar.
   2. `git pull --rebase` ile güncellen.
   3. **Yalnızca** ortak dosyaları içeren ayrı bir commit at: `CITYECHO_SHARED=1 git commit -m "..."`
   4. Hemen push et ve "çektim" demeyen olmadan bir sonrakine geçme.
4. **Veritabanı değişiklikleri** `db/schema.sql`'e değil `db/migrations/`'a gider: A `1xx_*.sql`, B `2xx_*.sql`, C `3xx_*.sql`. Push edilmiş bir migration bir daha **düzenlenmez**; düzeltme yeni bir migration ile yapılır.
5. **Yeni dosya** `OWNERS`'taki bir desene uymuyorsa commit engellenir. Önce `OWNERS`'a (SHARED commit'iyle) eklenmeli.
6. **Sözleşmeler** (kişiler arasındaki fonksiyon, sütun ve endpoint isimleri) `docs/ROADMAP.md` → "Sözleşmeler" bölümünde sabit. Tek taraflı değiştirilmez.
7. **OpenAPI ve otomatik üretilen tipler commit edilmez.**
8. **Gizli anahtarlar:** yalnızca `.env` dosyasına (gitignored). Asla commit etme, ekrana yazdırma.
9. **Commit mesajlarına** `Co-Authored-By: Claude` veya "Generated with Claude Code" satırı **ekleme**.
10. **Hook'u atlama.** `--no-verify` kullanma; hook bir şeyi engelliyorsa sebebini çöz.

## 3. Kurulum (her bilgisayarda bir kez)

```bash
git clone https://github.com/K0yr0/cityecho.git && cd cityecho
git config core.hooksPath .githooks       # sahiplik kontrolü her commit'te çalışır
git config cityecho.role A                # kendi rolün: A, B ya da C
git config pull.rebase true               # pull her zaman rebase yapar
python3 scripts/check_owners.py --all     # "0 sahipsiz" demeli
```

Sonra backend kurulumu (bölüm 7).

## 4. Günlük git akışı (herkes doğrudan main'e push eder)

```bash
git pull                                  # 1. işe başlamadan önce
# ... yalnızca kendi dosyalarında çalış ...
.venv/bin/pytest                          # 2. testler geçmeden push yok
git add <kendi dosyaların> && git commit  # 3. hook başkasının dosyasını engeller
git pull && .venv/bin/python scripts/init_db.py   # 4. başkalarının migration'larını al
git push                                  # 5. küçük ve sık push
```

- **Asla** `git push --force` yapma, başkasının commit'ini geri alma.
- Herkes yalnızca kendi dosyalarına yazdığı için `git pull` (rebase) çakışma üretmez. Çakışma çıkarsa bu bir kural ihlalidir: dosyanın sahibine sor, kendin çözme.
- `main`'e yapılan her push Vercel'i yeniden yayınlar. Web'i bozan bir push herkesi etkiler, bu yüzden B web build'ini (`npm run build`) push'tan önce çalıştırır.

## 5. Alınan kararlar (yeniden tartışma)

- Kullanıcı tarafı **mobil uygulama** (Expo), admin tarafı **web** (Next.js).
- **Gerçek sensör / ESP32 yok. Her şey simülasyon.** Kişi C, sanal otobüslerin sensör verisini üretir (`scripts/simulate_buses.py`) ve `/devices/stream` endpoint'ine gerçek bir cihaz gibi gönderir. Sunumda verinin simüle olduğu açıkça söylenir.
- Web'deki `/ride` telefon kayıt sayfası **silinecek**.
- Giriş öncesi kazanılan güven puanı, Google girişinde **hesaba taşınır**.
- Admin **tüm departmanları** görür (ZDM, Tramwaje Warszawskie, MPWiK, Straż Miejska).
- "Çevrende çukur görüyor musun?" sorusunun yarıçapı **25 m**. Yalnızca telefonun GPS isabeti ≤ 25 m olduğunda sorulur.
- İki ayrı durum alanı var, karıştırma: **güven durumu** (candidate / likely / verified / dismissed, motor belirler) ve **iş durumu** `work_status` (yapılmadı / devam ediyor / yapıldı, belediye belirler).
- **"Yapıldı" işaretlenince:** soru durur, güven puanları kapatılır, onarımdan sonra gelen HAYIR cevapları kimsenin aleyhine sayılmaz.
- Kullanıcı sensör verisi, kanıt zaman çizelgesi ve olgular **görmez**; bunlar yalnızca adminde. Kullanıcı yol sağlığını **yalnızca renk** olarak görür.

## 6. Öncelik sırası

**Gün 0 tamamlandı** (ortak temel, giriş iskeleti, migration'lar, Docker, harita verisi, mobil iskeleti, `web-admin/` taşıması). Üç kişi aynı anda başlar:

```
A → M0 → M1 → M2 → M3 → M4 → M5 → M6 (→ M7)
B → W0 → W1 → W2 → W3 → W4 → W5
C → S1 → S2 → S3 → S4 → S5        (S0 harita: bitti)
```

Görevlerin içeriği: `docs/ROADMAP.md`. Gün 0 sözleşmeleri (giriş, roller, `work_status`, `/devices/stream` formatı, kısa olay görünümü): `docs/ARCHITECTURE.md` §8.

## 7. Çalıştırma

**Kolay yol: Docker** (Docker Desktop kurulu olmalı; ayrıntı: `docker/README.md`):
```bash
cp .env.example .env                              # isteğe bağlı anahtarlar
docker compose up --build                         # veritabanı + backend + web admin
# http://localhost:3000  (web admin)   http://localhost:8000/docs  (API)
docker compose --profile seed run --rm seed       # demo şikayetleri ve sürüşleri yükle
docker compose down -v                            # her şeyi sıfırla
```
Docker henüz gerçek bir makinede denenmedi. İlk çalıştıran sorun çıkarsa SHARED commit'iyle düzeltir.

**Docker'sız yol:**
```bash
python3.11 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
brew install postgresql@18 postgis && createdb cityecho
.venv/bin/python scripts/init_db.py                                                   # her git pull'dan sonra
.venv/bin/python scripts/load_osm.py --from-geojson data/osm/segments_demo.geojson --skip-if-loaded   # harita, saniyeler
.venv/bin/uvicorn backend.main:app --reload                                           # http://localhost:8000/docs
cd web-admin && npm install && npm run dev                                            # http://localhost:3000
```

**Mobil** (A; Docker dışında): `cd mobile && npm install && npx expo start`, telefonda Expo Go. Telefon için `mobile/.env` içinde `EXPO_PUBLIC_API_URL=http://<bilgisayarın-LAN-IP'si>:8000`. Node 22 veya 24 önerilir (23 uyarı verir).

`.env` içeriği (her kişinin kendi `.env`'i olur, paylaşılmaz):
- `DATABASE_URL=postgresql://localhost:5432/cityecho`
- `WARSAW_API_KEY`: api.um.warszawa.pl hesabındaki uzun `eyJ...` token (herkes kendi hesabından alır)
- `NOMINATIM_USER_AGENT`: gerçek e-posta adresi
- `ANTHROPIC_API_KEY`: isteğe bağlı; yoksa anahtar kelime yedeği çalışır
- `GOOGLE_CLIENT_IDS`, `AUTH_SECRET`, `ADMIN_EMAILS`: Google girişi (A kurar). Yerelde Google olmadan denemek için `AUTH_DEV_LOGIN=1` → `POST /auth/dev {"email": ...}`
- `DEVICE_KEYS`: sanal otobüs cihaz anahtarları (C)

## 8. Mevcut durum (bu dosyayı güncel tut)

- ✅ Backend: sensör hattı, şikayet triyajı, füzyon, güven motoru, güven puanı (trust), doğrulama döngüsü. 200 test geçiyor (`.venv/bin/pytest`).
- ✅ Gün 0: tüm router'lar kayıtlı; giriş iskeleti (`backend/auth/`: `current_user`, `require_admin`, Google + dev girişi, güvenin hesaba taşınması); migration sistemi ve 100/200/300 migration'ları (`users`, `work_status`, `devices`); Docker; mobil iskeleti (Expo SDK 57).
- ✅ Web arayüzü `web-admin/` içinde. Kullanıcı sayfaları hâlâ içinde; B, W0'da siler.
- ✅ Herkese açık demo sitesi: https://cityecho-gules.vercel.app (demo verisiyle).
- ✅ Canlı Varşova araç konumları çalışıyor (yeni API, aşağıya bak).
- ✅ Sahiplik kontrolü: `OWNERS` + `.githooks/pre-commit` + `scripts/check_owners.py`.
- ✅ Harita (S0): 11.833 segment (9.057 yol, 2.776 ray), gerçek kırılganlık verisiyle; `data/osm/segments_demo.geojson` repoda, yükleme saniyeler sürer. Demo tramvay sürüşleri gerçek raylarla hizalı (%100).
- ⏳ `/devices/stream` 501 döndürüyor (C, S1'de yazar); `scripts/simulate_buses.py` henüz yok (C, S2).
- ❌ Bilinen eksik: tramvay, yol çukurunu doğrulayamıyor (tramvay tespitleri yalnızca ray olaylarıyla eşleşir). Simüle otobüsler yol çukurlarını doğrular.
- ❌ Bilinen eksik (B ve C): tramvay hattı iki paralel raydan oluşuyor; bir sürüşün GPS'i iki ray arasında gidip geliyor. Füzyonun "≥ 2 sürüş aynı segmentte" kuralı iki rayı tek sayacak şekilde ele alınmalı.
- ℹ️ `nearest_segment(...)` Marszałkowska'da en yakın yolu ~16 m'de, rayı ~24 m'de buluyor; yalnızca ray ararken 50 m yarıçap gerekebilir.

## 9. Tuzaklar

- **Varşova canlı araç API'si değişti.** Adres: `POST https://dane.um.warszawa.pl/api/action/get_ztm_lokalizacja_pojazdow`, gövde `{"type": 1|2}` (1 = otobüs, 2 = tramvay), token `Authorization` başlığında. Eski `busestrams_get` + `apikey=` artık çalışmıyor. Kod bunu kullanıyor (`backend/fusion/verify.py`).
- **Overpass (OpenStreetMap) yavaş** ve sık zaman aşımına uğruyor. İndirmeler `data/cache/osmnx` içinde önbelleğe alınıyor.
- `frontend/AGENTS.md`: bu Next.js sürümünde API'ler değişmiş olabilir. Yeni Next özelliği yazmadan önce `node_modules/next/dist/docs/` belgelerine bak.
- Doğruluk sayıları (kategori %97 vb.) **sentetik veriden** geliyor. Sunumda "simülasyonda ölçüldü" diye sun.
