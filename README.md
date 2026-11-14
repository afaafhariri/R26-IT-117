# BuildWise — AI-Driven Construction Planner for Sri Lankan Residential Buildings

Research project R26-IT-117.

Four services take a residential project from a cadastral survey plan to a
monitored construction schedule. A gateway authenticates the browser and fronts
the services, and a React wizard drives them in order.

| Component | Folder | What it does | Stack, port | Docs |
|---|---|---|---|---|
| C01 Architectural Planning | [`architecture/`](architecture/) | Cadastral plan → site data, buildable zone, floor plans, BuildingSchema | FastAPI + Celery, `:8001` | [README](architecture/README.md) |
| C02 Cost Estimation | [`cost-estimation/`](cost-estimation/) | BuildingSchema → BOQ, rates, ML cost prediction with risk bands | FastAPI, `:8002` | [README](cost-estimation/README.md) |
| C03 Timeline Prediction | [`timeline/`](timeline/) | Cost output → phase durations, Gantt, critical path | FastAPI, `:8000` | [README](timeline/README.md) |
| C04 Performance Monitoring | [`performance/`](performance/) | Planned schedule + progress → delay prediction, RAG recommendations | Flask, `:5004` | [README](performance/README.md) |
| Gateway | [`gateway/`](gateway/) | Sign-up, login, sessions; forwards `/api/c01…c04/…` | FastAPI, `:8080` | [README](gateway/README.md) |
| Web | [`web/`](web/) | The planner wizard; orchestrates C01 → C04 through the gateway | React + Vite, `:5173` | [README](web/README.md) |

## Repository layout

```
R26-IT-117/
├── architecture/       # C01 — FastAPI app, stages/, routers/, scripts/ (NER + RAG tooling)
├── cost-estimation/    # C02 — FastAPI app, layers/, models/, scripts/ (training)
├── timeline/           # C03 — FastAPI app in app/, models/, data/ (training set)
├── performance/        # C04 — Flask app, pipeline/, rag/, models/, data/
├── gateway/            # Auth + reverse proxy, Alembic migrations for authdb
├── web/                # React wizard (pnpm)
├── shared/schemas/     # site_schema.json, building_schema.json — the C01 → C02 contract
└── docker-compose.yml  # postgres, performance, gateway, mailpit
```

Folder names are lowercase and hyphenated. Python packages (folders with
`__init__.py`) keep underscores, because Python can't import a hyphenated name.

## Data flow

```
Cadastral plan  →  C01 Architecture  →  BuildingSchema  →  C02 Cost Estimation
                                                                 ↓
                               C04 Performance  ←  schedule  ←  C03 Timeline
```

The services don't call each other: the web app calls each one in turn and
passes each step's output forward. See [web/README.md](web/README.md).

## Python environments

Every Python component is its own [uv](https://docs.astral.sh/uv/) project, with
its own `pyproject.toml`, `uv.lock`, `.python-version` (3.12) and `.venv`. The
repo root is not a Python project and has no virtual environment.

```bash
cd <component>
uv sync                  # create/update .venv from uv.lock (installs Python 3.12 if needed)
uv run <command>         # run inside that .venv, no activation needed
uv add <package>==<ver>  # add a dependency (updates pyproject.toml and uv.lock)
```

Commit `pyproject.toml` and `uv.lock` together. Optional dependency groups:
`uv sync --group train` in `performance/` (offline training) and
`uv sync --group scripts` in `architecture/` (data scripts).

## Running locally

1. Postgres and Mailpit (and C04 + the gateway, if you want them containerised):

   ```bash
   docker compose up -d postgres mailpit
   ```

   The gateway's `authdb` must be created once — see
   [gateway/README.md](gateway/README.md#docker).

2. The services, each from its own folder:

   ```bash
   cd gateway         && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8080
   cd architecture    && uv sync && uv run uvicorn main:app --port 8001   # + Redis and a Celery worker, see its README
   cd cost-estimation && uv sync && uv run uvicorn main:app --port 8002
   cd timeline        && uv sync && uv run uvicorn app.main:app --port 8000
   cd performance     && uv sync && uv run python main.py
   ```

3. The web app:

   ```bash
   cd web && pnpm install && pnpm dev   # http://localhost:5173
   ```

Each service reads its own `.env` (copy its `.env.example`).

## Docker

Every component has a two-stage `Dockerfile`: uv installs the locked
dependencies in a build stage, and the runtime image gets only the virtual
environment and the app (no uv, build tools, tests, training data or scripts;
see each `.dockerignore`). Torch is installed from the CPU-only index on Linux.

`docker-compose.yml` runs `postgres`, `performance`, `gateway` and `mailpit`.
C01–C03 are built and run on their own (`docker build -t <name> ./<component>`);
the gateway container reaches them on the host through `host.docker.internal`.

## Tests

```bash
cd <component> && uv run pytest
```

The gateway's auth tests and one C04 module need Postgres (see their READMEs).
