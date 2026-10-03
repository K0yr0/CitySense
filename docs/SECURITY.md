# Security review: open findings (2026-10-04)

Status: **found, not fixed yet.** Each finding has an owner. Fix only your own files; shared ones go
through a SHARED commit (CLAUDE.md §2). Mark a finding ✅ here when it is fixed.

**Intended, not a finding:** `/rides/upload` and `/rides/stream` accept rides without a device key.
The simulation and the mock data (C) depend on that. Keep these endpoints local (Docker), never on a
public deployment.

**What is already fine:** session tokens (fixed HS256, issuer, required expiry), no secret ever
committed, the phone keeps its token in secure storage, the whole `/admin` router requires an admin,
all `/mobile/*` write endpoints require sign-in, photos are anonymised, SQL is parameterised.

---

## 📱 Person A

### A1. Anyone can vote on any problem, from anywhere 🔴 High
- **Where:** `backend/api/responses.py`, `POST /incidents/{id}/responses`
- **Problem:** the old web voting endpoint needs no sign-in and no location (the 25 m rule does not
  apply), and every new random "contributor" token counts as a new person.
- **Abuse:** a script sends "NO" 50 times with 50 random tokens; the confidence engine sees 50
  citizens and moves the problem to `dismissed`, which is final, so it disappears for good. "YES"
  works the other way and pushes fake problems up.
- **Fix:** the app uses `/mobile/incidents/{id}/answer` (sign-in + 25 m) and the web admin has no
  citizen pages any more, so remove this endpoint, or require sign-in plus the same 25 m check.
- **Affects C:** the S6 contract lists this endpoint; C switches to `/mobile/incidents/{id}/answer`.

### A2. Anonymous complaint spam 🔴 High
- **Where:** `backend/api/reports.py`, `POST /reports` and `POST /reports/bulk`
- **Problem:** both take complaints without sign-in; bulk takes hundreds per request; each complaint
  also counts as a YES vote.
- **Abuse:** one bulk request with 1,000 invented complaints creates fake problems all over the city,
  buries the real queue, inflates the statistics and loads the server (triage + geocoding).
- **Fix:** `/reports` requires sign-in (the app already uses `/mobile/reports`); `/reports/bulk`
  becomes admin-only.
- **Affects C:** the mock seeder calls `/reports/bulk` with the admin token from dev sign-in.

### A3. Dev sign-in can make anyone an admin 🔴 High (shared Wi-Fi)
- **Where:** `backend/auth/routes.py`, `POST /auth/dev` (together with S1: Docker turns it on)
- **Problem:** dev sign-in accepts any email; an email in `ADMIN_EMAILS` becomes admin. Docker always
  enables it, and the API is reachable on the network (needed for the phone).
- **Abuse:** on the hackathon Wi-Fi someone sends `POST http://<laptop-ip>:8000/auth/dev
  {"email": "<admin email>"}` and is admin: marks problems done, settles everyone's trust.
- **Fix:** dev sign-in requires a team-only secret: `AUTH_DEV_LOGIN` holds a secret value in `.env`
  (not `1`) and the request must send it in a header. Teammates and the mock seeder have it.
- **Affects C:** the mock seeder sends that header.

### A4. Spoofed GPS can get around the 25 m rule 🟠 Medium (cannot be fully removed)
- **Where:** `/mobile/question`, `/mobile/incidents/{id}/answer`
- **Problem:** the server trusts the location the phone reports; fake-GPS apps exist.
- **Already limited by:** Google sign-in (one account = one person), one answer per problem,
  trust weighting, the citizen cap (citizens alone cannot reach `verified`).
- **Optional fix:** a daily answer limit per user; reject impossible jumps (far away minutes ago,
  at the problem now). For the pitch, say it openly.

## 🖥️ Person B

### B1. Admin data in a public API 🟠 Medium (personal data, GDPR)
- **Where:** `backend/api/incidents.py`, `GET /incidents`, `GET /incidents/{id}`,
  `POST /incidents/{id}/verify`
- **Problem:** the web admin has a login screen, but these endpoints have no check of their own.
- **Abuse:** anyone opens `http://<server>:8000/incidents/42` and reads raw complaint texts (people
  write names and phone numbers), photos, sensor signals and the evidence timeline, which citizens
  must not see. Spamming `/verify` triggers many Warsaw vehicle-API calls.
- **Fix:** add `require_admin` to these three endpoints. The web admin already sends its Bearer token
  (`web-admin/lib/api.ts`), so only the backend changes. The app uses `/mobile/incidents` (public
  fields only) and is not affected.
- **Affects C:** if the mock seeder reads these endpoints, it uses the admin token.

## 📡 Person C

No finding of C's own (the ride endpoints are intended, see the top). C updates the S6 seeder for
A1, A2, A3 and B1 once they are fixed; the S6 contract table in `docs/ROADMAP.md` is updated in the
same SHARED commit.

## 🔗 Shared (one person, SHARED commit, announced in the group)

### S1. The Docker database is open to the network with a default password 🔴 High (shared Wi-Fi)
- **Where:** `docker-compose.yml`, port `"5433:5432"`, password `cityecho` (in the repo)
- **Abuse:** anyone on the same Wi-Fi runs `psql -h <laptop-ip> -p 5433 -U cityecho` and can read,
  change or delete everything.
- **Fix:** `"127.0.0.1:5433:5432"`. Only this computer reaches the database; the API still reaches
  it inside Docker. One line, no side effects.

### S2. Error messages reveal internals 🟡 Low
- **Where:** `backend/main.py` (`"internal error: TypeError: ..."`)
- **Fix:** send only `"internal error"` to the client; the details already go to the log.

### S3. No rate limiting 🟡 Low
- **Problem:** sign-in, complaints and answers accept unlimited requests.
- **Fix:** a simple limiter (e.g. `slowapi`): sign-in 10/min, complaints 5/min, answers 30/min.
  Not urgent for the hackathon; mention it as a next step in the pitch.

### S4. Phone ↔ API over plain HTTP 🟡 Low (demo practice)
- **Problem:** in the demo the phone talks to `http://<laptop-ip>:8000`; on shared Wi-Fi the sign-in
  token is readable.
- **Fix:** run the phone and the laptop on your own phone's hotspot during the demo. No code change.

---

## Suggested order

1. S1 and A3 (most urgent before the hackathon Wi-Fi, both small)
2. A1 and A2 (tell C first: the S6 contract changes)
3. B1
4. S2, S4, then A4 and S3 if there is time
