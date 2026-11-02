"""Loads the local data snapshot (CSV files produced by scripts/fetch_data.py).

Why a snapshot instead of calling Elexon on every request?
  * January 2026 is history - the data will not change, so there is no point re-fetching it.
  * The deployed app (Vercel serverless) starts fast and never depends on Elexon being up.
  * Every reviewer sees exactly the same numbers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from . import config
from .analysis import to_utc


class DataNotAvailable(RuntimeError):
    """Raised when the snapshot files have not been created yet."""


@dataclass(frozen=True)
class DataStore:
    actuals: pd.DataFrame  # columns: startTime, actual
    forecasts: pd.DataFrame  # columns: publishTime, startTime, forecast
    meta: dict


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    for path in (config.ACTUALS_FILE, config.FORECASTS_FILE):
        if not path.exists():
            raise DataNotAvailable(
                f"Data file {path.name} not found. Create it with:  python -m backend.scripts.fetch_data"
            )

    actuals = pd.read_csv(config.ACTUALS_FILE)
    actuals["startTime"] = to_utc(actuals["startTime"])
    actuals = actuals.rename(columns={"generation": "actual"})[["startTime", "actual"]]
    actuals = actuals.drop_duplicates("startTime", keep="last").sort_values("startTime").reset_index(drop=True)

    forecasts = pd.read_csv(config.FORECASTS_FILE)
    forecasts["startTime"] = to_utc(forecasts["startTime"])
    forecasts["publishTime"] = to_utc(forecasts["publishTime"])
    forecasts = forecasts.rename(columns={"generation": "forecast"})[["publishTime", "startTime", "forecast"]]
    forecasts = forecasts.drop_duplicates(["publishTime", "startTime"], keep="last")
    forecasts = forecasts.sort_values(["startTime", "publishTime"]).reset_index(drop=True)

    meta = {}
    if config.META_FILE.exists():
        meta = json.loads(config.META_FILE.read_text())

    return DataStore(actuals=actuals, forecasts=forecasts, meta=meta)
