# planner-ui — R26-IT-117 Construction Planner

React 18 + TypeScript + Vite. A 4-step wizard plus a review page that drives
Components 02, 03 and 04.

## Why the frontend does the orchestration

The backend services **do not call each other**. Apart from one fire-and-forget
call from C01 to C02, no service makes any outbound HTTP request to another —
there is no orchestrator and no bus. The gateway (`gateway/`) only forwards
each request to one service; it never chains them.

So this app is the orchestrator: it calls each service in turn and passes each
step's output forward as the next step's input.

It is also the **store**. C02 and C03 persist nothing — they compute a response
and forget it. Only C04 keeps state. Everything the review page shows lives in
`localStorage` under the key `r26.run`.

## Running

Start the gateway and the three backends first (C01 is not required — see below):

| Service | Port | Start from |
|---|---|---|
| Gateway | 8080 | `gateway/` → `.venv/bin/python -m uvicorn app.main:app --port 8080` (needs `authdb`, see its README) |
| Mailpit | 8025 | repo root → `docker compose up -d mailpit` (catches the sign-up and reset emails) |
| C02 Cost Estimation | 8002 | `cost-estimation/` → `.venv/bin/python -m uvicorn main:app --port 8002` |
| C03 Timeline | 8000 | `timeline/` → `.venv/bin/python -m uvicorn app.main:app --port 8000` |
| C04 Performance | 5004 | `performance/` → `.venv/bin/python main.py` (needs Postgres) |

Then:

```bash
pnpm install
pnpm dev            # http://localhost:5173
```

The browser only calls `/api/<service>/…` on its own origin. Vite forwards
`/api` to the gateway (`http://localhost:8080` by default; set `GATEWAY_URL` in
`.env` to change it), and the gateway knows where each service lives. The old
`VITE_C0x_URL` variables are no longer read.

## Accounts

Every step needs a signed-in user; the landing page and the account pages
(`/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password`)
don't. Signing up sends a confirmation link (read it in Mailpit locally), and
confirming asks for the password again, then signs you in.

The session is an HttpOnly cookie the page can't read; `GET /api/auth/me` is
how the app knows who is signed in. If any service call comes back 401 (the
session timed out), the app sends you to log in and back to the same page.

The saved run in `localStorage` is tied to the account: logging out clears it,
and signing in as someone else starts a fresh one. Signing back in as the same
user keeps it.

## The steps

1. **Design** — a local stand-in for C01, which is not wired up yet. C01's only
   downstream output is a `BuildingSchema`, so this form produces one directly.
   Nothing after this step can tell the difference. To swap in the real C01:
   `POST /process-cadastral` → `POST /generate-floorplans` → poll
   `GET /floorplans/status/{id}` → `POST /select-plan`, then take
   `FullDesignPackage.building_schema_json`.
2. **Materials & Cost** — `GET /materials` builds the picker; `POST /estimate`
   prices it. Changing a material re-prices automatically (debounced).
3. **Timeline** — `POST /api/timeline/predict`. The response carries
   `performance_monitoring_payload`, which is the exact body step 4 needs.
4. **Performance** — `POST /schedule` seeds the baseline once, then
   `POST /progress/spi` and `POST /progress/predict` record progress and run the
   delay model.
5. **Review** — reads only from `localStorage`, no network calls.

## Things that will bite you

- **The UI makes no cross-origin calls.** Everything goes through the gateway,
  which also strips the services' own CORS headers. `CORS_ALLOW_ORIGINS` in C02
  and C03 now only matters for tools that call those services directly.
- **C04 rejects the predict step unless SPI is WARNING or CRITICAL.** A phase
  whose planned start is in the future always scores SPI 1.00, so the delay model
  cannot run on it. Pick a phase already underway and enter a percentage below
  its expected progress.
- **C04's delay model was trained on a subset**: 14 of 25 districts, and 4
  provinces — spelled *with* the `" Province"` suffix (`"Southern Province"`,
  not `"Southern"`). Step 1 warns when the chosen location is unsupported.
- **C04's `sub_phase` vocabulary does not match what C03 emits.** C03 sends
  `"Columns, beams and slab work"`; the model knows `"Columns & beams"`.
  `"Painting"` and `"Client handover"` are not in its vocabulary at all. Only
  some phases can currently be scored. This is a backend data-contract issue,
  not a frontend one.
- **C04 mints its own integer `project_id`**, unrelated to the id sent to C03.
  It is captured into `run.step4.c04ProjectId`.
- **`POST /schedule` is marked TEMPORARY / DEV-ONLY** in C04's source and refuses
  to run when `TIMELINE_SOURCE=remote`.
- **Confidence is scaled inconsistently** — C03 returns 0–1, C04 returns 0–100.
  The `pct()` helper in `components/ui.tsx` normalises both.
- C04 needs its FAISS index built once, or `/progress/predict` returns a 500:
  ```bash
  ./.venv/bin/python -c "from rag.faiss_index import build_index; build_index()"
  ```

## Layout

```
src/
  api/client.ts      fetch wrapper; surfaces backend validation detail
  api/services.ts    one typed function per endpoint
  state/runStore.ts  localStorage persistence + step gating
  types/index.ts     types mirroring the live API responses
  components/        Stepper, shared UI primitives
  pages/             Step1Design … Step4Performance, Review
```
