# planner-ui — R26-IT-117 Construction Planner

React 18 + TypeScript + Vite. A 4-step wizard plus a review page that drives
Components 02, 03 and 04.

## Why the frontend does the orchestration

The backend services **do not call each other**. Apart from one fire-and-forget
call from C01 to C02, no service makes any outbound HTTP request to another —
there is no orchestrator, no bus, no gateway that chains them.

So this app is the orchestrator: it calls each service in turn and passes each
step's output forward as the next step's input.

It is also the **store**. C02 and C03 persist nothing — they compute a response
and forget it. Only C04 keeps state. Everything the review page shows lives in
`localStorage` under the key `r26.run`.

## Running

Start the three backends first (C01 is not required — see below):

| Component | Port | Start from |
|---|---|---|
| C02 Cost Estimation | 8002 | `cost-estimation/` → `./.venv/bin/uvicorn main:app --port 8002` |
| C03 Timeline | 8000 | `timeline/` → `./.venv/bin/uvicorn app.main:app --port 8000` |
| C04 Performance | 5004 | `performance/` → `./.venv/bin/python main.py` (needs Postgres) |

Then:

```bash
pnpm install
pnpm dev            # http://localhost:5173
```

Base URLs come from `.env` (`VITE_C02_URL` etc.), never hardcoded.

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

- **C02 and C03 both needed CORS changes** to accept requests from `:5173`.
  Both now read `CORS_ALLOW_ORIGINS` (comma-separated) if you deploy elsewhere.
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
