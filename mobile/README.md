# CityEcho mobil (Kişi A)

Vatandaşın kullandığı uygulama. Expo SDK 57, React Native 0.86, TypeScript, Expo Router.
Görevler: `docs/ROADMAP.md` → M0–M7.

> **Sahiplik:** Bu klasör (`mobile/**`) ve `OWNERS` içinde A'ya yazılı backend dosyaları
> (`backend/auth/**`, `backend/api/users.py`, `responses.py`, `reports.py`, `mobile.py`, `backend/triage/**`,
> `db/migrations/1*` …) senin. Başka bir dosyada değişiklik gerekiyorsa sahibine söyle, kendin değiştirme.

## Çalıştırma

Node 22 LTS ya da 24 önerilir.

1. **Önce backend'i çalıştır** (repo kökünde). Telefonun erişebilmesi için `0.0.0.0` üzerinde dinlemeli:
   ```bash
   .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   # ya da Docker ile:
   docker compose up
   ```
2. **Backend adresini ayarla:**
   ```bash
   cd mobile
   cp .env.example .env
   ```
   `.env` içinde `EXPO_PUBLIC_API_URL` değerine bilgisayarının LAN IP'sini yaz, ör.
   `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000`. IP'yi bulmak için macOS'ta `ipconfig getifaddr en0`,
   Windows'ta `ipconfig` kullan. Telefonda `localhost` telefonun kendisi demek, bu yüzden çalışmaz.
   Boş bırakılırsa `http://localhost:8000` kullanılır (yalnızca web ve simülatör).
3. **Uygulamayı başlat:**
   ```bash
   npm install
   npx expo start
   ```
4. **Telefonda aç:** Expo Go uygulamasını kur, telefon ve bilgisayar **aynı Wi-Fi**'da olsun, terminaldeki
   QR kodunu okut. Harita sekmesi "● Bağlı" ve canlı tramvay sayısını göstermeli.

`.env` değiştikten sonra önbelleği temizleyerek yeniden başlat: `npx expo start --clear`.

Tarayıcıda denemek için `npx expo start --web` (http://localhost:8081). Bu durumda backend'in kendi `.env`'inde
`CORS_ORIGINS` değerine `http://localhost:8081` eklenmeli; telefon uygulaması için CORS gerekmez.

## Kontroller (push'tan önce)

```bash
npx tsc --noEmit     # tipler
npx expo lint        # lint
npx expo-doctor      # bağımlılık ve yapılandırma
```

Yeni paket eklerken `npm install` değil `npx expo install <paket>` kullan (SDK'ya uygun sürümü seçer).
Expo Go yalnızca kendi içindeki native modülleri çalıştırır; başka native kod içeren bir kütüphane
eklenirse development build gerekir (`AGENTS.md`).

## Yapı

```
src/app/_layout.tsx            kök Stack (ileride olay detayı gibi ekranlar buraya eklenir)
src/app/(tabs)/_layout.tsx     alt sekmeler: Harita, Bildir, Rotalarım, Profil
src/app/(tabs)/index.tsx       Harita  → M1 (şimdilik backend bağlantı kontrolü)
src/app/(tabs)/report.tsx      Bildir  → M3
src/app/(tabs)/routes.tsx      Rotalarım → M5
src/app/(tabs)/profile.tsx     Profil  → M2
src/lib/api.ts                 backend istemcisi (getHealth, getLiveVehicles); yeni endpoint'ler buraya
src/components/                backend-status, placeholder, themed-text, themed-view
src/constants/theme.ts         renkler ve boşluklar
```

API sözleşmeleri: `docs/ARCHITECTURE.md` §6. Harita, kimlik doğrulama, kamera ve konum kütüphaneleri
henüz kurulu değil; seçim senin.
