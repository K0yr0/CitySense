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
   QR kodunu okut. Harita (Map) sekmesinde olay pinleri görünmeli.

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

## Diller

Uygulama **İngilizce, Lehçe ve Ukraynaca** (Türkçe yok). İlk açılışta telefonun dili Lehçe ya da Ukraynaca ise o,
değilse İngilizce seçilir; Profile sekmesinin en üstündeki seçiciden değiştirilir ve cihazda saklanır.

- Metinler `src/i18n/<alan>.ts` dosyalarında: `{ en, pl, uk }`; `pl` ve `uk` `typeof en` tipinde, eksik anahtar derleme hatası verir.
- Bileşende `const s = useText(reportText)`, bileşen dışında `text(reportText)`. Sayılı ifadeler için `plural(n, {one, few, many, other})`
  (Lehçe/Ukraynaca: 1 / 2–4 / 5+).
- Ortak kelimeler `src/i18n/common.ts`, olay türü/durum/yol sağlığı sözlüğü `src/i18n/labels.ts`.
- Backend'in kısa durum mesajları (`message`) `Accept-Language` başlığına göre en/pl/uk gelir (`backend/api/mobile.py` → `TEXTS`).
- iOS izin metinleri: `app.json` (İngilizce) + `locales/pl.json`, `locales/uk.json`.

## Giriş (M2)

- **Demo girişi** (Expo Go dahil her yerde): backend `.env` içinde `AUTH_DEV_LOGIN=1` olmalı. Profile → Sign in →
  bir e-posta yaz. Yalnızca yerel test ve demo için; canlıda kapalı tutulur.
- **Google ile giriş** Expo Go'da çalışmaz (native kod gerekir). Development build ister
  (`npx expo run:ios` / `npx expo run:android` ya da `eas build --profile development`) ve:
  1. Google Cloud Console → OAuth istemci kimlikleri: Web (origin `http://localhost:8081`, yönlendirme
     `http://localhost:8081/sign-in`), iOS (bundle id `com.cityecho.app`), Android (paket `com.cityecho.app` + SHA-1;
     gelişmiş ayarlarda "custom URI scheme" açık).
  2. `mobile/.env`: `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`.
  3. Backend `.env`: `GOOGLE_CLIENT_IDS=<web>,<ios>,<android>`.
- Giriş öncesi cihazda bir anonim katkıcı anahtarı tutulur; girişte gönderilir, kazanılan güven puanı hesaba taşınır.

## Yapı

```
src/app/_layout.tsx               kök Stack + SessionProvider + 25 m sorusu (her ekranın üstünde)
src/app/(tabs)/index.tsx          Harita (M1): anlık konum + isabet halkası, yol sağlığı yalnızca renk, olay pinleri
src/app/(tabs)/report.tsx         Bildir (M3): metin, kamera/galeri, konum → kısa durum
src/app/(tabs)/routes.tsx         Rotalarım (M5): favori rotalar listesi
src/app/(tabs)/profile.tsx        Profil (M2): güven puanı, bildirimlerim, çıkış
src/app/sign-in.tsx               Giriş (M2): Google + demo girişi (modal)
src/app/incident/[id].tsx         Kısa olay görünümü (M6): tür, adres, güven etiketi, belediyenin iş durumu
src/app/route/new.tsx, [id].tsx   Rota ekle / rota boyunca yol kalitesi ve "ileride kötü yol" uyarısı (M5)
src/components/<ekran>/           ekranlara özel bileşenler (map, report, routes, incident, profile, question)
src/components/question/          25 m sorusu kartı (M4)
src/hooks/use-location.ts         konum (expo-location); konum geçmişi tutulmaz
src/hooks/use-nearby-question.ts  25 m sorusu mantığı (isabet ≤ 25 m, olay başına bir kez, yapıldıysa sorma)
src/lib/api.ts                    backend istemcisi (tüm /mobile uç noktaları); yeni endpoint'ler buraya
src/lib/session.tsx               oturum, token, cihaz katkıcı anahtarı
src/lib/labels.ts                 etiketler (geçerli dilde) ve renkler (güven durumu ≠ iş durumu)
src/lib/i18n.tsx                  dil seçimi, useText/text, plural
src/i18n/                         en/pl/uk metinleri (alan başına bir dosya)
src/lib/geo.ts, storage.ts        geometri yardımcıları, cihazda güvenli saklama
```

Backend tarafı (A): `backend/api/mobile.py` (`/mobile/*`), `backend/auth/`, `db/migrations/101_favorite_routes.sql`,
testler `backend/tests/test_mobile_api.py`. Vatandaş hiçbir zaman sensör verisi, kanıt, zaman çizelgesi ya da
başkalarının rapor metnini görmez (ARCHITECTURE.md §8.4).
