# CityEcho mobile (person A)

The citizens' app. Expo SDK 57, React Native 0.86, TypeScript, Expo Router.
Tasks: `docs/ROADMAP.md` → M0–M7.

> **Ownership:** this folder (`mobile/**`) and the backend files assigned to A in `OWNERS`
> (`backend/auth/**`, `backend/api/users.py`, `responses.py`, `reports.py`, `mobile.py`, `backend/triage/**`,
> `db/migrations/1*` …) are yours. If another file needs a change, tell its owner; don't change it yourself.

## Running

Node 22 LTS or 24 recommended.

1. **Start the backend first** (repo root). It must listen on `0.0.0.0` so the phone can reach it:
   ```bash
   .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   # or with Docker:
   docker compose up
   ```
2. **Set the backend address:**
   ```bash
   cd mobile
   cp .env.example .env
   ```
   In `.env`, set `EXPO_PUBLIC_API_URL` to your computer's LAN IP, e.g.
   `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000`. Find the IP with `ipconfig getifaddr en0` on macOS or
   `ipconfig` on Windows. On a phone, `localhost` means the phone itself, so it doesn't work there.
   When empty, `http://localhost:8000` is used (web and simulator only).
3. **Start the app:**
   ```bash
   npm install
   npx expo start
   ```
4. **Open it on the phone:** install Expo Go, put the phone and the computer on the **same Wi-Fi**, and scan the
   QR code in the terminal. The Map tab should show incident pins.

After changing `.env`, restart with a clean cache: `npx expo start --clear`.

To try it in a browser: `npx expo start --web` (http://localhost:8081). The backend's own `.env` must then list
`http://localhost:8081` in `CORS_ORIGINS`; the phone app doesn't need CORS.

## Checks (before pushing)

```bash
npx tsc --noEmit     # types
npx expo lint        # lint
npx expo-doctor      # dependencies and config
```

Add packages with `npx expo install <package>`, not `npm install` (it picks the SDK-compatible version).
Expo Go only runs the native modules it ships with; a library with other native code needs a
development build (`AGENTS.md`).

## Languages

The app is in **English, Polish and Ukrainian**. On first launch it follows the phone's language when that is
Polish or Ukrainian, otherwise English; the picker at the top of the Profile tab changes it, and the choice is
stored on the device.

- Texts live in `src/i18n/<area>.ts` as `{ en, pl, uk }`; `pl` and `uk` are typed as `typeof en`, so a missing key
  is a compile error.
- In a component `const s = useText(reportText)`, outside components `text(reportText)`. Counted nouns use
  `plural(n, {one, few, many, other})` (Polish/Ukrainian: 1 / 2–4 / 5+).
- Shared words: `src/i18n/common.ts`; the glossary for incident type, status and road health: `src/i18n/labels.ts`.
- The backend's short status messages (`message`) come in en/pl/uk according to the `Accept-Language` header
  (`backend/api/mobile.py` → `TEXTS`).
- iOS permission texts: `app.json` (English) + `locales/pl.json`, `locales/uk.json`.

## Maps and icons

- **Android uses Leaflet, not Google Maps.** In Expo Go, Google rejects Expo Go's built-in Maps key
  ("Authorization failure" in logcat) and the Google map then draws nothing, not even our lines and pins.
  `src/components/map-canvas/` gives every screen one declarative map API (polylines, circles, pins, events):
  `map-canvas.tsx` = react-native-maps / Apple Maps (iOS), `map-canvas.android.tsx` = Leaflet in a WebView with
  OpenStreetMap tiles (no key; attribution shown). A development build with its own Google Maps key could switch back.
- **No emoji as icons.** Emoji depend on the device's emoji font (the iOS 26 simulator draws them as "?" boxes).
  Use `<Icon name=... />` / `<TypeIcon type=... />` from `src/components/icon.tsx`.

## Sign-in (M2)

- **Demo sign-in** (works everywhere, Expo Go included): the backend `.env` needs `AUTH_DEV_LOGIN=1`.
  Profile → Sign in → enter an email. Local testing and demos only; keep it off in production.
- **Google sign-in** doesn't work in Expo Go (it needs native code). It requires a development build
  (`npx expo run:ios` / `npx expo run:android` or `eas build --profile development`) and:
  1. Google Cloud Console → OAuth client IDs: Web (origin `http://localhost:8081`, redirect
     `http://localhost:8081/sign-in`), iOS (bundle id `com.cityecho.app`), Android (package `com.cityecho.app` + SHA-1;
     "custom URI scheme" enabled in the advanced settings).
  2. `mobile/.env`: `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`.
  3. Backend `.env`: `GOOGLE_CLIENT_IDS=<web>,<ios>,<android>`.
- Before sign-in the device keeps an anonymous contributor token; it is sent at sign-in, so trust earned
  anonymously carries over to the account.

## Structure

```
src/app/_layout.tsx               root Stack + I18nProvider + SessionProvider + 25 m question (above every screen)
src/app/(tabs)/index.tsx          Map (M1): current location + accuracy ring, road health as colour only, incident pins
src/app/(tabs)/report.tsx         Report (M3): text, camera/gallery, location → short status
src/app/(tabs)/routes.tsx         My routes (M5): favourite routes list
src/app/(tabs)/profile.tsx        Profile (M2): language, trust score, my reports, sign out
src/app/sign-in.tsx               Sign in (M2): Google + demo sign-in (modal)
src/app/incident/[id].tsx         Short incident view (M6): type, address, confidence label, the city's work status
src/app/route/new.tsx, [id].tsx   Add route / road quality along the route and "bad road ahead" warnings (M5)
src/components/<screen>/          screen-specific components (map, report, routes, incident, profile, question)
src/components/question/          25 m question card (M4)
src/components/map-canvas/        every map: Apple Maps on iOS, Leaflet + OpenStreetMap in a WebView on Android
src/components/icon.tsx           vector icons (SF Symbols / Material); use these instead of emoji
src/hooks/use-location.ts         location (expo-location); no location history is kept
src/hooks/use-nearby-question.ts  25 m question logic (accuracy ≤ 25 m, once per incident, never when fixed)
src/lib/api.ts                    backend client (all /mobile endpoints); add new endpoints here
src/lib/session.tsx               session, token, device contributor token
src/lib/labels.ts                 labels (in the current language) and colours (confidence status ≠ work status)
src/lib/i18n.tsx                  language choice, useText/text, plural
src/i18n/                         en/pl/uk texts (one file per area)
src/lib/geo.ts, storage.ts        geometry helpers, secure on-device storage
```

Backend side (A): `backend/api/mobile.py` (`/mobile/*`), `backend/auth/`, `db/migrations/101_favorite_routes.sql`,
tests in `backend/tests/test_mobile_api.py`. Citizens never see sensor data, evidence, timelines or other people's
report texts (ARCHITECTURE.md §8.4).
