"""FastAPI application: thin HTTP layer on top of backend.analysis.

All routes live under /api so that the same URLs work
  * locally (Vite dev server / nginx proxy forward /api -> this app), and
  * on Vercel (a rewrite sends /api/* to this app).
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import analysis, config
from .data_store import DataNotAvailable, get_store

HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
WINDOW_START = date.fromisoformat(config.DELIVERY_START)
WINDOW_END = date.fromisoformat(config.DELIVERY_END)

app = FastAPI(
    title="Wind forecast accuracy API",
    description="Day-ahead wind generation forecasts vs actuals (Elexon FUELHH / WINDFOR), GB, January 2026.",
    version="1.0.0",
    docs_url="/api/docs",  # keep Swagger under /api so it is reachable behind the Vercel/nginx proxies too
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],  # dev only; production is same-origin
    allow_methods=["GET"],
    allow_headers=["*"],
)
router = APIRouter(prefix="/api")


def _store():
    try:
        return get_store()
    except DataNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _check_day(d: date, name: str) -> date:
    if not (WINDOW_START <= d <= WINDOW_END):
        raise HTTPException(status_code=400, detail=f"{name} must be between {WINDOW_START} and {WINDOW_END}")
    return d


def _check_range(start: date, end: date) -> None:
    _check_day(start, "start")
    _check_day(end, "end")
    if end < start:
        raise HTTPException(status_code=400, detail="end must not be before start")


@lru_cache(maxsize=32)
def _cached_sweep(start: date, end: date, step_hours: int) -> list[dict]:
    """The horizon sweep runs ~49 as-of joins, so remember results (inputs never change at runtime)."""
    store = get_store()
    return analysis.horizon_sweep(store.actuals, store.forecasts, start, end, step_hours=step_hours)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/meta")
def meta() -> dict:
    """Describes the data snapshot and the defaults the UI should start with."""
    store = _store()
    return {
        "source": store.meta.get("source", "unknown"),
        "fetched_at": store.meta.get("fetched_at"),
        "delivery_start": config.DELIVERY_START,
        "delivery_end": config.DELIVERY_END,
        "default_decision_time": config.DEFAULT_DECISION_TIME,
        "default_days_before": config.DEFAULT_DAYS_BEFORE,
        "max_horizon_hours": config.MAX_HORIZON_HOURS,
        "actuals_rows": int(len(store.actuals)),
        "forecast_rows": int(len(store.forecasts)),
        "forecast_publish_times": int(store.forecasts["publishTime"].nunique()),
        "actuals_range": store.meta.get("actuals_range"),
        "forecast_publish_range": store.meta.get("forecast_publish_range"),
    }


@router.get("/decision")
def decision(
    date_: date = Query(..., alias="date", description="Delivery day, YYYY-MM-DD"),
    decision_time: str = Query(config.DEFAULT_DECISION_TIME, pattern=HHMM_PATTERN, description="UK local time, HH:MM"),
    days_before: int = Query(config.DEFAULT_DAYS_BEFORE, ge=1, le=3),
) -> dict:
    """The forecast a buyer had on the morning before delivery, plus how it compared with reality."""
    _check_day(date_, "date")
    store = _store()
    return analysis.delivery_day_view(store.actuals, store.forecasts, date_, days_before, decision_time)


@router.get("/accuracy/day-ahead")
def accuracy_day_ahead(
    decision_time: str = Query(config.DEFAULT_DECISION_TIME, pattern=HHMM_PATTERN),
    days_before: int = Query(config.DEFAULT_DAYS_BEFORE, ge=1, le=3),
    start: date = Query(WINDOW_START),
    end: date = Query(WINDOW_END),
) -> dict:
    """Accuracy of the day-ahead decision forecast over a range of delivery days."""
    _check_range(start, end)
    store = _store()
    return analysis.day_ahead_accuracy(store.actuals, store.forecasts, start, end, days_before, decision_time)


@router.get("/accuracy/horizon")
def accuracy_horizon(
    horizon_hours: int = Query(24, ge=0, le=config.MAX_HORIZON_HOURS, description="Forecast made at least this many hours ahead"),
    start: date = Query(WINDOW_START),
    end: date = Query(WINDOW_END),
) -> dict:
    """Actual vs forecast for one fixed horizon, with error statistics and breakdowns."""
    _check_range(start, end)
    store = _store()
    pairs = analysis.horizon_pairs(store.actuals, store.forecasts, horizon_hours, start, end)
    return {
        "horizon_hours": horizon_hours,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metrics": analysis.compute_metrics(pairs),
        "series": analysis.series_rows(pairs),
        "histogram": analysis.error_histogram(pairs),
        "by_hour": analysis.error_by_hour(pairs),
        "by_level": analysis.error_by_level(pairs),
    }


@router.get("/accuracy/by-horizon")
def accuracy_by_horizon(
    start: date = Query(WINDOW_START),
    end: date = Query(WINDOW_END),
    step_hours: int = Query(1, ge=1, le=12),
) -> dict:
    """How does error grow as the forecast looks further ahead? (h = 0 ... MAX_HORIZON_HOURS)"""
    _check_range(start, end)
    _store()  # raises a friendly 503 if the data snapshot is missing
    return {"rows": _cached_sweep(start, end, step_hours)}


app.include_router(router)
