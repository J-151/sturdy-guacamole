"""Tiny client for the public Elexon BMRS "Insights" API (no API key needed).

Docs: https://bmrs.elexon.co.uk/api-documentation
We only use two *stream* endpoints, which return a plain JSON array:
  * FUELHH  - half-hourly generation outturn by fuel type (we keep fuelType == WIND)
  * WINDFOR - national wind generation forecasts, with publishTime and startTime
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from . import config

TIMEOUT_SECONDS = 120
MAX_RETRIES = 4


def _get_json(client: httpx.Client, url: str, params: dict) -> list[dict]:
    """GET with retries + exponential back-off. Returns the list of records."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            payload = resp.json()
            # Stream endpoints return a bare list; regular endpoints wrap it in {"data": [...]}
            if isinstance(payload, dict):
                payload = payload.get("data", [])
            return payload
        except (httpx.HTTPError, ValueError) as exc:  # network error, bad status, bad JSON
            last_error = exc
            wait = 2**attempt
            print(f"  ! attempt {attempt}/{MAX_RETRIES} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Elexon request failed after {MAX_RETRIES} attempts: {url} {params}") from last_error


def _chunks(start: date, end: date, days: int):
    """Yield (chunk_start, chunk_end) date windows covering [start, end] inclusive."""
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def _iso_z(d: date, end_of_day: bool = False) -> str:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if end_of_day:
        dt += timedelta(days=1)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_wind_actuals(start: date, end: date) -> pd.DataFrame:
    """Actual national wind generation (MW) per half hour: columns startTime, generation."""
    rows: list[dict] = []
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        for c_start, c_end in _chunks(start, end, days=7):
            print(f"FUELHH  settlement dates {c_start} -> {c_end}")
            params = {
                "settlementDateFrom": c_start.isoformat(),
                "settlementDateTo": c_end.isoformat(),
                "fuelType": "WIND",
            }
            rows.extend(_get_json(client, config.FUELHH_STREAM, params))

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Elexon returned no FUELHH rows - check the date range / API status.")
    df = df[df["fuelType"] == "WIND"]  # belt and braces in case the filter was ignored
    df = df[["startTime", "generation"]].copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna().drop_duplicates("startTime", keep="last").sort_values("startTime")

    # SAFETY CHECK. If a query parameter name is wrong, Elexon does not complain - it silently
    # returns the *latest* data instead. So we verify we really got the dates we asked for.
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end + timedelta(days=1), tz="UTC")
    df = df[(df["startTime"] >= lo) & (df["startTime"] < hi)]
    expected = ((end - start).days + 1) * 48
    if len(df) < 0.95 * expected:
        raise RuntimeError(
            f"Expected about {expected} half-hourly WIND rows between {start} and {end} but only "
            f"{len(df)} came back inside that range. Elexon may have ignored the date parameters "
            "(it returns the latest data when it does). Check the FUELHH/stream parameters in the Swagger docs."
        )
    return df.reset_index(drop=True)


def fetch_wind_forecasts(publish_from: date, publish_to: date) -> pd.DataFrame:
    """All WINDFOR forecast rows published in the window: publishTime, startTime, generation."""
    rows: list[dict] = []
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        for c_start, c_end in _chunks(publish_from, publish_to, days=2):
            print(f"WINDFOR publish times {c_start} -> {c_end}")
            params = {
                "publishDateTimeFrom": _iso_z(c_start),
                "publishDateTimeTo": _iso_z(c_end, end_of_day=True),
            }
            rows.extend(_get_json(client, config.WINDFOR_STREAM, params))

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Elexon returned no WINDFOR rows - check the date range / API status.")
    df = df[["publishTime", "startTime", "generation"]].copy()
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna().drop_duplicates(["publishTime", "startTime"], keep="last")

    # SAFETY CHECK (see fetch_wind_actuals): make sure we received forecasts from the whole window
    # we asked for, not just "the latest forecast".
    lo = pd.Timestamp(publish_from, tz="UTC")
    hi = pd.Timestamp(publish_to + timedelta(days=1), tz="UTC")
    df = df[(df["publishTime"] >= lo) & (df["publishTime"] < hi)]
    n_days = (publish_to - publish_from).days + 1
    n_issues = df["publishTime"].nunique()
    if n_issues < n_days:  # Elexon publishes several forecasts per day, so this is a very low bar
        raise RuntimeError(
            f"Expected several WINDFOR forecast issues per day between {publish_from} and {publish_to} "
            f"but only found {n_issues} distinct publish times. Elexon may have ignored the "
            "publishDateTimeFrom/To parameters."
        )
    return df.sort_values(["startTime", "publishTime"]).reset_index(drop=True)
