"""OFFLINE DEVELOPMENT ONLY: generate *synthetic* data with the same shape as the Elexon data.

    python -m backend.scripts.make_sample_data

Used by the unit tests and handy if you want to try the UI before running fetch_data.
The snapshot is tagged source="synthetic" and the UI shows a red banner when it is in use,
so it can never be mistaken for real data. Never deploy it.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config
from backend.scripts.fetch_data import _write


def build_synthetic(seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-12-25", tz="UTC")
    end = pd.Timestamp("2026-02-02", tz="UTC")
    times = pd.date_range(start, end, freq="30min", inclusive="left")

    # Smooth "weather": an AR(1) process mapped into [800, 14000] MW
    x = np.zeros(len(times))
    for i in range(1, len(times)):
        x[i] = 0.995 * x[i - 1] + rng.normal(0, 0.12)
    z = (x - x.min()) / (x.max() - x.min())
    actual = 800 + 13200 * z**1.3
    truth = pd.Series(actual, index=times)

    # A forecast published every 3 hours, covering the next 72 hours. Error grows with lead time.
    rows = []
    for pub in pd.date_range(start, end - pd.Timedelta(hours=1), freq="3h"):
        targets = pd.date_range(pub + pd.Timedelta(minutes=30), pub + pd.Timedelta(hours=72), freq="30min")
        targets = targets[targets < end]
        lead_h = (targets - pub) / pd.Timedelta(hours=1)
        sigma = 250 + 70 * lead_h
        fc = truth.reindex(targets).to_numpy() + rng.normal(0, 1, len(targets)) * sigma + 150
        rows.append(pd.DataFrame({"publishTime": pub, "startTime": targets, "generation": np.clip(fc, 0, None)}))
    forecasts = pd.concat(rows, ignore_index=True)

    window_start = pd.Timestamp(config.DELIVERY_START, tz="UTC")
    window_end = pd.Timestamp(date.fromisoformat(config.DELIVERY_END) + timedelta(days=1), tz="UTC")
    forecasts = forecasts[(forecasts["startTime"] >= window_start) & (forecasts["startTime"] < window_end)]
    actuals = truth.rename("generation").rename_axis("startTime").reset_index()
    actuals = actuals[(actuals["startTime"] >= window_start) & (actuals["startTime"] < window_end)]
    return actuals, forecasts.reset_index(drop=True)


def main(out_dir: Path | None = None) -> None:
    actuals, forecasts = build_synthetic()
    if out_dir is not None:  # lets tests write somewhere temporary
        config.DATA_DIR = out_dir
        config.ACTUALS_FILE = out_dir / "actuals.csv"
        config.FORECASTS_FILE = out_dir / "forecasts.csv.gz"
        config.META_FILE = out_dir / "meta.json"
    meta = _write(actuals, forecasts, source="synthetic")
    print("Wrote SYNTHETIC sample data:", meta)


if __name__ == "__main__":
    main()
