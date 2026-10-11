# Backend hand-off to P4 (web app)

The backend is live on AWS (Mumbai, `ap-south-1`) with the real pipeline: P2 imagery → P1 roof model → P2 solar
simulation. You can build against it now instead of (or alongside) MSW mocks. Questions/changes: P3.

## 0. What you need installed

Only **Node.js (LTS) and Git**. You do **not** need the AWS CLI, Docker, Python, CDK or AWS credentials: the web app
talks to the deployed API over HTTPS like any browser. Deploying the backend stays with P3. Amplify Hosting is set up
in the AWS console of P3's account (P3 does it, or gives you a console login limited to Amplify).

## 1. Settings for `web/.env.production` / `.env.development`

P3 sends these (also written by `infra/scripts/export_env.py` to `web/.env.production`):

```
VITE_API_URL=https://0cw3tjdvo2.execute-api.ap-south-1.amazonaws.com
VITE_USER_POOL_ID=ap-south-1_TDZMa24oN
VITE_USER_POOL_CLIENT_ID=3l16lr73pip6o9sbbnk258vbb7
VITE_REGION=ap-south-1
VITE_USE_MOCKS=false
```
None of these are secrets (the app client has no secret), but keep `.env*` out of git as usual.

## 2. Login (Amplify v6)

```ts
import { Amplify } from "aws-amplify";
import { fetchAuthSession } from "aws-amplify/auth";

Amplify.configure({
  Auth: { Cognito: {
    userPoolId: import.meta.env.VITE_USER_POOL_ID,
    userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
    loginWith: { email: true },
  } },
});

export async function api(path: string, init: RequestInit = {}) {
  const { tokens } = await fetchAuthSession();
  const res = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens?.idToken?.toString()}`, ...init.headers },
  });
  const body = await res.json();
  if (!res.ok) throw Object.assign(new Error(body.error ?? body.message ?? res.statusText), { status: res.status, body });
  return body;
}
```

- `<Authenticator>` sign-up works as is: e-mail + password (min 8, upper/lower/digit), then a 6-digit code by e-mail.
  Cognito's built-in e-mail sender allows **50 e-mails/day** for the whole pool; fine for the demo.
- Every new user is put in **Homeowner** automatically. **Installer** accounts are promoted by P3
  (`infra/scripts/make_installer.sh <email>`); the user must sign out/in afterwards.
- Role badge: `tokens.idToken.payload["cognito:groups"]` (array, may be missing for a brand-new session).

## 3. API

Full spec: [`contracts/openapi.yaml`](../contracts/openapi.yaml). Every route needs the token. Errors are always `{"error": "..."}`.

| Call | Returns | Notes |
|---|---|---|
| `POST /jobs` `{address}` or `{lat, lng}` | `201 {job_id}` | 400 if outside Delhi/NCR (lat 28.4–28.9, lng 76.8–77.4) or address not found; 429 after 20 jobs/day (Installer 100) |
| `GET /jobs/{id}` | `{job_id, status, address, lat, lng, created_at, ...}` | `status`: `queued → fetching → segmenting → simulating → done` or `failed` (+ `error`). When `done`: `report` (contract C) and `heatmap_png_url` |
| `GET /jobs` | `{jobs: [...]}` newest first | done jobs include `kw_dc`, `annual_kwh`, `payback_years` (for the installer table) |
| `POST /jobs/batch` `{addresses: [string or {lat,lng}]}` | `201 {job_ids}` | Installer only (**403 for Homeowners**: Cedar). Max 25. If any entry is invalid → 400 with `invalid: [{index, input, error}]` and nothing is created |

**Polling:** `GET /jobs/{id}` every 3 s until `done`/`failed`. Typical time **15–25 s**; the **first job after the
system has been idle can take ~2 min** (cold start) — show the stepper, don't time out before 5 min.

**Failures to show nicely:** `"No roof found at this location..."` (pin not on a roof), `"timed out ..."`, quota 429,
outside-Delhi 400.

## 4. Rendering the report (contract C)

Example: [`contracts/fixtures/report_C.json`](../contracts/fixtures/report_C.json) (schema `contracts/schemas/C.schema.json`).

- **Panels:** `report.panels` is a GeoJSON FeatureCollection (WGS84, `[lng, lat]`) → MapLibre `fill`/`line` layer.
- **Shade heatmap:** `heatmap_png_url` (presigned, **valid 15 min** — re-`GET` the job to refresh) is a transparent PNG
  for `report.heatmap_bounds = [minLng, minLat, maxLng, maxLat]`. MapLibre image source coordinates:
  `[[minLng, maxLat], [maxLng, maxLat], [maxLng, minLat], [minLng, minLat]]`. Don't use `heatmap_png_s3_uri` (not public).
- **KPIs:** `building.usable_area_m2`, `system.kw_dc`, `system.panel_count`, `energy.annual_kwh`,
  `finance.annual_savings_inr`, `finance.payback_years` (**can be `null`** = no finite payback, show "—"),
  `co2_t_per_year`; monthly chart from `energy.monthly_kwh` (12 values); finance card from `finance.*`.
- **Assumptions/data sources:** `report.assumptions` (includes `warnings`, show them) and `report.data_sources`.
- Roof/obstacle outlines are not in C; if you want them, ask P3 to add `seg_B` to the response.

## 5. Things P3 must do for you

- **CORS:** the API and the heatmap bucket currently allow only `http://localhost:5173`. Send P3 your Amplify URL
  (e.g. `https://main.xxxx.amplifyapp.com`) and P3 redeploys with it.
- Promote Installer test accounts (`make_installer.sh`).
- Address autocomplete is not an API route yet; use free-text address or a map click (`{lat, lng}`).
  Geocoded addresses can land on the neighbour's roof, so let the user confirm/move the pin before submitting.
