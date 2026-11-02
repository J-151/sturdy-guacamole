"""Download the January 2026 data from Elexon and save it as a small local snapshot.

Run from the project root:

    python -m backend.scripts.fetch_data

Creates (in backend/data/):
    actuals.csv        startTime, generation            (FUELHH, fuelType = WIND)
    forecasts.csv.gz   publishTime, startTime, generation (WINDFOR)
    meta.json          where / when the data came from
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from backend import config
from backend.elexon import fetch_wind_actuals, fetch_wind_forecasts


def _write(actuals: pd.DataFrame, forecasts: pd.DataFrame, source: str) -> dict:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%Y-%m-%dT%H:%M:%SZ"

    a = actuals.copy()
    a["startTime"] = a["startTime"].dt.strftime(fmt)
    a.to_csv(config.ACTUALS_FILE, index=False)

    f = forecasts.copy()
    f["startTime"] = f["startTime"].dt.strftime(fmt)
    f["publishTime"] = f["publishTime"].dt.strftime(fmt)
    f.to_csv(config.FORECASTS_FILE, index=False, compression="gzip")

    meta = {
        "source": source,  # "elexon" for real data
        "fetched_at": datetime.now(timezone.utc).strftime(fmt),
        "delivery_window": [config.DELIVERY_START, config.DELIVERY_END],
        "actuals_rows": int(len(actuals)),
        "forecast_rows": int(len(forecasts)),
        "forecast_publish_times": int(forecasts["publishTime"].nunique()),
        "actuals_range": [actuals["startTime"].min().strftime(fmt), actuals["startTime"].max().strftime(fmt)],
        "forecast_publish_range": [forecasts["publishTime"].min().strftime(fmt), forecasts["publishTime"].max().strftime(fmt)],
    }
    config.META_FILE.write_text(json.dumps(meta, indent=2))
    return meta


def main() -> None:
    d_start = date.fromisoformat(config.DELIVERY_START)
    d_end = date.fromisoformat(config.DELIVERY_END)

    actuals = fetch_wind_actuals(d_start, d_end)
    forecasts = fetch_wind_forecasts(
        date.fromisoformat(config.FORECAST_PUBLISH_FROM), date.fromisoformat(config.FORECAST_PUBLISH_TO)
    )

    # Keep only what a January-2026 buyer could use:
    #  - targets inside the delivery window (UTC == UK time in January)
    #  - forecasts published before their own target time
    window_start = pd.Timestamp(d_start, tz="UTC")
    window_end = pd.Timestamp(d_end + timedelta(days=1), tz="UTC")
    forecasts = forecasts[(forecasts["startTime"] >= window_start) & (forecasts["startTime"] < window_end)]
    forecasts = forecasts[forecasts["publishTime"] <= forecasts["startTime"]]
    actuals = actuals[(actuals["startTime"] >= window_start) & (actuals["startTime"] < window_end)]

    meta = _write(actuals, forecasts, source="elexon")
    print("\nSaved snapshot to", config.DATA_DIR)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
