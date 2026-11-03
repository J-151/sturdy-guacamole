# Day-ahead wind forecast portal (GB, January 2026)

A web app that helps a UK energy buyer answer two questions before placing a day-ahead order:

1. **What wind forecast did I actually have when I had to decide?**
2. **How wrong are those forecasts, so I can plan around the error?**

Scope follows the brief: national-level wind only, from two Elexon BMRS datasets.
**FUELHH** (`fuelType = WIND`) gives actual generation and **WINDFOR** gives forecasts (each with a `publishTime`). Delivery days are 1-31 January 2026.

| | |
|---|---|
| Live app | `https://sturdy-guacamole-five.vercel.app/` |
| Video demo | `<PASTE UNLISTED YOUTUBE URL>` |
| Stack | React 18 + TypeScript + Vite + Recharts · Python 3.12 + FastAPI + pandas · Docker · Vercel |

---

## AI assistance (please read)

AI tools were used while building this project. I used **Claude (Anthropic)** as an assistant, most notably for:

- **Docker setup.** I had not used Docker before, so the Dockerfiles, `docker-compose.yml`, nginx config and container start-up script were created with Claude's help, and I learned how they work by working through them.
- **The Python backend.** I have not worked professionally with Python, so Claude helped with the FastAPI / pandas implementation, project structure and unit tests.
- General guidance on deployment configuration and documentation.

I reviewed and ran the code, and I explain the design, analysis and code base in the video (part 2).

---

## What the app shows

**Day-ahead decision tab.** Choose a delivery day and the time the order is placed on the day before (default 09:00 UK). The chart shows the newest forecast that had been published *by that time*, plus a likely range (P10-P90) learned only from earlier days. A toggle reveals what actually happened (hindsight). A table lists which forecast issues (publish times) fed the view.

**Forecast accuracy tab.**
- Accuracy of the day-ahead decision forecast for every day in January (MAE, RMSE, bias, P90 error, an "over-forecast buffer"), per-day bars, error distribution, error by hour.
- Error vs forecast horizon (0-48 h): how quickly forecasts degrade the further ahead they look.
- A horizon explorer (slider): actual vs forecast for the whole month, plus error by hour and by wind level.

### Key assumptions (all easy to change in `backend/config.py`)

| Topic | Assumption |
|---|---|
| "Decisions made in January 2026" | Delivery days 1-31 Jan 2026. (If you read it as decisions *taken* in January, delivery would be 2 Jan - 1 Feb; change `DELIVERY_START/END` and re-run the fetch script.) |
| Decision time | 09:00 UK time on the day before delivery. GB day-ahead auctions close mid-morning on D-1; the time is adjustable in the UI. |
| Which forecast is "available" | The newest forecast for that half-hour with `publishTime <= decision time`. |
| Error sign | `error = forecast - actual`. Positive = wind over-estimated (the risky direction for a buyer, who would under-buy). |
| Time zone | Elexon times are UTC. UK time = UTC in January (GMT), so there are no daylight-saving effects in this window. |

### Metrics

- **MAE**: mean absolute error (MW). **RMSE**: penalises big misses. **Bias**: mean error.
- **WMAPE** = sum(|error|) / sum(actual). Plain MAPE explodes when wind is near zero, so it is not used.
- **P90 absolute error**: 90% of half-hours missed by less than this.
- **Over-forecast buffer**: the 90th percentile of (forecast - actual), floored at 0. Roughly: "holding back this much of the forecast wind would have covered 9 out of 10 half-hours". It is an empirical statement about January 2026, not a guarantee.
- **Likely range** on the decision chart: forecast + P10/P90 of past (actual - forecast), using only days whose outcome was known at decision time (no look-ahead). Needs 2+ earlier days, so it is hidden for 1-3 Jan.

---

## Repository layout

```
.
├── README.md
├── docker-compose.yml          # runs backend + frontend together
├── requirements.txt            # Python runtime dependencies (Docker + Vercel)
├── requirements-dev.txt        # + pytest
├── vercel.json                 # Vercel settings for the BACKEND project
├── api/
│   └── index.py                # Vercel entry point: exposes the FastAPI app
├── backend/
│   ├── main.py                 # FastAPI routes (thin HTTP layer)
│   ├── analysis.py             # all the maths: as-of join, metrics, decision view (pure pandas)
│   ├── data_store.py           # loads the CSV snapshot into DataFrames
│   ├── elexon.py               # Elexon API client (retries, chunking, sanity checks)
│   ├── config.py               # dates, cutoff default, paths, URLs
│   ├── Dockerfile
│   ├── data/                   # data snapshot (actuals.csv, forecasts.csv.gz, meta.json)
│   ├── scripts/
│   │   ├── fetch_data.py       # downloads real data from Elexon -> backend/data
│   │   ├── start.py            # container start-up (fetch data if missing, run server)
│   │   └── make_sample_data.py # SYNTHETIC data for offline development/tests only
│   └── tests/                  # pytest: analysis logic, API, Elexon client
├── frontend/
│   ├── package.json, vite.config.ts, tsconfig.json, index.html
│   ├── Dockerfile, nginx.conf  # build with Node, serve with nginx, proxy /api to backend
│   ├── vercel.json             # Vercel settings for the FRONTEND project
│   └── src/
│       ├── App.tsx             # tabs + shared state
│       ├── api.ts, types.ts    # typed API client
│       ├── hooks.ts            # useAsync (loading/error/cancel stale requests)
│       ├── format.ts, theme.ts, styles.css
│       └── components/
│           ├── DecisionView.tsx, AccuracyView.tsx
│           ├── charts.tsx      # all Recharts charts
│           └── ui.tsx          # StatStrip, Section, Panel, Status
└── .github/workflows/ci.yml    # runs tests + frontend build on every push
```

### Why a data snapshot?

January 2026 is history, so the app downloads it once (`fetch_data.py`) and stores a small snapshot in `backend/data/`. This keeps the deployed app fast, independent of Elexon being available, and means every viewer sees identical numbers. The snapshot is committed to the repo.

---

## How to run

### Option A: Docker (recommended)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) running.

```bash
docker compose up --build
```

- First start: the backend downloads the data from Elexon (about 1-3 minutes). Watch progress with `docker compose logs -f backend`.
- Open **http://localhost:8080** (web app) or **http://localhost:8000/api/docs** (API docs).
- Data is saved to `backend/data/` on your machine, so later starts are instant.
- Stop with `Ctrl+C`, remove containers with `docker compose down`.

### Option B: run locally without Docker

Requirements: Python 3.12+, Node 20+.

```bash
# 1. Backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m backend.scripts.fetch_data # one-off: downloads real data into backend/data/
uvicorn backend.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173  (proxies /api to port 8000)
```

### Tests

```bash
python -m pytest backend/tests -q    # 21 tests
cd frontend && npm run build         # type-checks and builds
```

To try the UI without internet you can run `python -m backend.scripts.make_sample_data` (writes **synthetic** data, and the UI then shows a red banner). Never commit or deploy that data.

---

## API

All routes are under `/api` (interactive docs at `/api/docs`).

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness check |
| `GET /api/meta` | data source, counts, defaults |
| `GET /api/decision?date=2026-01-15&decision_time=09:00` | forecast available at decision time for one delivery day, band, versions used, accuracy |
| `GET /api/accuracy/day-ahead?decision_time=09:00` | month-level accuracy of the decision forecast (daily, histogram, by hour/level) |
| `GET /api/accuracy/horizon?horizon_hours=24&start=&end=` | actual vs forecast series + metrics for a fixed horizon |
| `GET /api/accuracy/by-horizon?start=&end=` | MAE/RMSE/P90 for horizons 0-48 h |

---

## Deployment (Vercel)

The repo is deployed as **two Vercel projects** from the same GitHub repo, each zero-config:

1. **Backend (API)**: Root Directory = repo root (`./`). Vercel detects FastAPI and uses `api/index.py`. `vercel.json` bundles `backend/data/` and leaves out the frontend and tests.
2. **Frontend**: Root Directory = `frontend`, framework Vite. `frontend/vercel.json` rewrites `/api/*` to the backend URL, so the browser stays on one origin and no CORS setup is needed. Replace `REPLACE-WITH-YOUR-BACKEND-URL` in that file with the backend project's domain.

Make sure `backend/data/` (real data) is committed before deploying.

---

## Limitations and next steps

- The likely range uses one pooled error distribution. Wind-forecast error depends on the wind level, so a level-dependent band would be tighter at low wind.
- Only national totals are used (by design of the brief). Regional or per-farm data, demand and price data would be needed to turn "how much wind" into a full purchase recommendation.
- January 2026 is one month in one season. Error statistics should not be extrapolated to summer.
- The cutoff time is an assumption; the client's real gate-closure times should replace the default.

---

*Contains BMRS data © Elexon Limited copyright and database right 2026.*
