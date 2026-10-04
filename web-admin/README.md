# CitySense frontend

Next.js 16 (App Router, TypeScript, Tailwind 4) + MapLibre GL 6 + deck.gl 9 + recharts 3.
Codes against `docs/ARCHITECTURE.md` §6; types live in `lib/types.ts`.

```bash
npm install            # also copies the MapLibre worker into public/maplibre/
npm run dev:mock       # fixtures only (lib/mock.ts), no backend needed
npm run dev            # talks to NEXT_PUBLIC_API_URL (default http://localhost:8000)
npm run build && npm start
```

Copy `.env.local.example` to `.env.local` to configure. When the backend is unreachable,
every request falls back to the fixtures and the header shows a **Demo data** badge.

| Route | What |
|---|---|
| `/` | City health map: segment health, incidents (blue report / green sensor / orange both), live ZTM vehicles, stats funnel |
| `/incidents` | Priority queue with department and status filters |
| `/incidents/[id]` | Reports, photo, sensor signal chart, evidence timeline, "Request verification" |

Citizen pages (reporting, YES/NO answers, ride recording) live in the mobile app (`mobile/`), not here.

## Backend proxy

Set `NEXT_PUBLIC_API_URL=/api` to reach the backend through the built-in Next.js proxy
(`BACKEND_URL`, default `http://localhost:8000`), which avoids CORS and mixed-content errors.
