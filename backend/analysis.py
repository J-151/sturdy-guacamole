"""Analysis logic: "which forecast did we have?" and "how wrong was it?".

Everything here is a pure function of pandas DataFrames, so it is easy to unit test and
has no knowledge of FastAPI / HTTP.

Vocabulary used throughout
--------------------------
target time / startTime : the half hour that is being forecast (UTC, from Elexon)
publishTime             : when a forecast was created (UTC)
cutoff                  : the moment a decision is taken; only forecasts with
                          publishTime <= cutoff may be used
lead time               : startTime - publishTime (how far ahead the forecast looked)
error                   : forecast - actual   (positive = we OVER-estimated wind,
                          which is the risky direction for a buyer: we'd under-buy)

Two ways of choosing "the forecast we had":
1. decision rule  - latest forecast published before D-1 at HH:MM (what the buyer
                    really sees when the day-ahead auction closes)
2. horizon rule   - latest forecast published at least h hours before the target
                    (lets us study accuracy as a function of lead time)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import config

UTC_NS = "datetime64[ns, UTC]"
HALF_HOUR_MWH_FACTOR = 0.5  # MW sustained for 30 minutes = 0.5 MWh
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def to_utc(series: pd.Series) -> pd.Series:
    """Parse timestamps as UTC with nanosecond resolution (merge_asof needs identical dtypes)."""
    return pd.to_datetime(series, utc=True).astype(UTC_NS)


def parse_hhmm(value: str) -> tuple[int, int]:
    m = _HHMM.match(value)
    if not m:
        raise ValueError(f"decision time must look like 'HH:MM', got {value!r}")
    return int(m.group(1)), int(m.group(2))


def local_dates(start_times: pd.Series) -> pd.Series:
    """UK-local calendar date for each UTC timestamp (the 'delivery day')."""
    return start_times.dt.tz_convert(config.LOCAL_TZ).dt.date


def iso(series: pd.Series) -> pd.Series:
    return series.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(x) -> float | None:
    """NaN / inf -> None so that JSON serialisation never breaks."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(xf) or np.isinf(xf)) else round(xf, 3)


def target_grid(start_day: date, end_day: date) -> pd.DataFrame:
    """Every half hour of every delivery day from start_day to end_day inclusive."""
    start = pd.Timestamp(start_day).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    end = pd.Timestamp(end_day + timedelta(days=1)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    idx = pd.date_range(start, end, freq="30min", inclusive="left")
    return pd.DataFrame({"startTime": pd.Series(idx).astype(UTC_NS)})


# ---------------------------------------------------------------------------
# Choosing "the forecast that was available"
# ---------------------------------------------------------------------------
def latest_forecast_asof(targets: pd.DataFrame, forecasts: pd.DataFrame) -> pd.DataFrame:
    """For each target row pick the most recent forecast with publishTime <= cutoff.

    targets   : columns [startTime, cutoff]
    forecasts : columns [publishTime, startTime, forecast]
    returns   : [startTime, cutoff, publishTime, forecast]; publishTime/forecast are NaN
                when no forecast existed yet at the cutoff.

    This is a classic "as-of join": for every target half-hour we look backwards in time
    through the forecast history of *that same half-hour* and take the newest one that
    already existed at the cutoff.
    """
    left = targets.dropna(subset=["cutoff"]).sort_values("cutoff")
    right = forecasts[["publishTime", "startTime", "forecast"]].sort_values("publishTime")
    out = pd.merge_asof(
        left,
        right,
        left_on="cutoff",
        right_on="publishTime",
        by="startTime",
        direction="backward",
    )
    return out.sort_values("startTime").reset_index(drop=True)


def decision_cutoffs(start_times: pd.Series, days_before: int, decision_time: str) -> pd.Series:
    """Cutoff = (delivery day - days_before) at HH:MM UK local time, expressed in UTC."""
    hh, mm = parse_hhmm(decision_time)
    local_wall = start_times.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None)
    delivery_midnight = local_wall.dt.normalize()
    cutoff_wall = delivery_midnight - pd.Timedelta(days=days_before) + pd.Timedelta(hours=hh, minutes=mm)
    cutoff = cutoff_wall.dt.tz_localize(config.LOCAL_TZ, ambiguous="NaT", nonexistent="shift_forward")
    return cutoff.dt.tz_convert("UTC").astype(UTC_NS)


def _finish_pairs(df: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Attach actuals, lead time, error columns, and delivery date to a forecast selection."""
    df = df.merge(actuals[["startTime", "actual"]], on="startTime", how="left")
    df["lead_hours"] = (df["startTime"] - df["publishTime"]) / pd.Timedelta(hours=1)
    df["error"] = df["forecast"] - df["actual"]
    df["abs_error"] = df["error"].abs()
    df["local_date"] = local_dates(df["startTime"])
    return df


def horizon_pairs(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    horizon_hours: float,
    start_day: date,
    end_day: date,
    prefiltered: bool = False,
) -> pd.DataFrame:
    """Forecast/actual pairs where each forecast was published >= horizon_hours before its target.

    prefiltered=True means the caller already restricted `forecasts` to the target range
    (used by horizon_sweep so the filtering is not repeated 49 times).
    """
    grid = target_grid(start_day, end_day)
    grid["cutoff"] = grid["startTime"] - pd.Timedelta(hours=horizon_hours)
    fc = forecasts if prefiltered else forecasts[forecasts["startTime"].isin(grid["startTime"])]
    return _finish_pairs(latest_forecast_asof(grid, fc), actuals)


def decision_pairs(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    start_day: date,
    end_day: date,
    days_before: int,
    decision_time: str,
) -> pd.DataFrame:
    """Forecast/actual pairs using the day-ahead decision rule (see module docstring)."""
    grid = target_grid(start_day, end_day)
    grid["cutoff"] = decision_cutoffs(grid["startTime"], days_before, decision_time)
    fc = forecasts[forecasts["startTime"].isin(grid["startTime"])]
    return _finish_pairs(latest_forecast_asof(grid, fc), actuals)


# ---------------------------------------------------------------------------
# Accuracy metrics
# ---------------------------------------------------------------------------
def compute_metrics(pairs: pd.DataFrame) -> dict:
    """Quantitative accuracy summary. error = forecast - actual (MW)."""
    valid = pairs.dropna(subset=["forecast", "actual"])
    n = int(len(valid))
    empty = {
        "n": 0,
        "n_total": int(len(pairs)),
        "mean_actual_mw": None,
        "mae_mw": None,
        "rmse_mw": None,
        "bias_mw": None,
        "wmape_pct": None,
        "abs_error_p50_mw": None,
        "abs_error_p90_mw": None,
        "abs_error_p95_mw": None,
        "over_forecast_p90_mw": None,
        "under_forecast_p90_mw": None,
        "max_over_mw": None,
        "max_under_mw": None,
    }
    if n == 0:
        return empty

    err = valid["error"]
    abs_err = valid["abs_error"]
    total_actual = valid["actual"].sum()
    return {
        "n": n,
        "n_total": int(len(pairs)),
        "mean_actual_mw": _num(valid["actual"].mean()),
        "mae_mw": _num(abs_err.mean()),
        "rmse_mw": _num(np.sqrt((err**2).mean())),
        "bias_mw": _num(err.mean()),
        # Weighted MAPE = sum(|error|) / sum(actual). Unlike plain MAPE it does not
        # blow up when actual wind is close to zero.
        "wmape_pct": _num(abs_err.sum() / total_actual * 100) if total_actual > 0 else None,
        "abs_error_p50_mw": _num(abs_err.quantile(0.5)),
        "abs_error_p90_mw": _num(abs_err.quantile(0.9)),
        "abs_error_p95_mw": _num(abs_err.quantile(0.95)),
        # Planning buffers: "90% of the time we over-estimated wind by less than X MW"
        "over_forecast_p90_mw": _num(max(0.0, err.quantile(0.9))),
        "under_forecast_p90_mw": _num(max(0.0, -err.quantile(0.1))),
        "max_over_mw": _num(err.max()),
        "max_under_mw": _num(err.min()),
    }


def error_histogram(pairs: pd.DataFrame, bins: int = 24) -> list[dict]:
    valid = pairs.dropna(subset=["error"])
    if valid.empty:
        return []
    limit = max(500.0, np.ceil(max(abs(valid["error"].quantile(0.005)), abs(valid["error"].quantile(0.995))) / 500) * 500)
    counts, edges = np.histogram(valid["error"].clip(-limit, limit), bins=bins, range=(-limit, limit))
    return [
        {"from_mw": _num(edges[i]), "to_mw": _num(edges[i + 1]), "mid_mw": _num((edges[i] + edges[i + 1]) / 2), "count": int(c)}
        for i, c in enumerate(counts)
    ]


def error_by_hour(pairs: pd.DataFrame) -> list[dict]:
    valid = pairs.dropna(subset=["error"]).copy()
    if valid.empty:
        return []
    valid["hour"] = valid["startTime"].dt.tz_convert(config.LOCAL_TZ).dt.hour
    g = valid.groupby("hour")
    return [
        {"hour": int(h), "mae_mw": _num(grp["abs_error"].mean()), "bias_mw": _num(grp["error"].mean()), "n": int(len(grp))}
        for h, grp in g
    ]


LEVEL_EDGES = [0, 2000, 4000, 6000, 8000, 10000, 12000, np.inf]


def error_by_level(pairs: pd.DataFrame) -> list[dict]:
    """Does error depend on how windy it actually was? (bucketed by ACTUAL generation)"""
    valid = pairs.dropna(subset=["error"]).copy()
    if valid.empty:
        return []
    valid["bucket"] = pd.cut(valid["actual"], bins=LEVEL_EDGES, right=False)
    rows = []
    for bucket, grp in valid.groupby("bucket", observed=True):
        lo, hi = bucket.left, bucket.right
        label = f"{int(lo / 1000)}+ GW" if np.isinf(hi) else f"{int(lo / 1000)}-{int(hi / 1000)} GW"
        rows.append(
            {
                "label": label,
                "n": int(len(grp)),
                "mae_mw": _num(grp["abs_error"].mean()),
                "bias_mw": _num(grp["error"].mean()),
                "wmape_pct": _num(grp["abs_error"].sum() / grp["actual"].sum() * 100) if grp["actual"].sum() > 0 else None,
            }
        )
    return rows


def series_rows(pairs: pd.DataFrame) -> list[dict]:
    out = pd.DataFrame(
        {
            "t": iso(pairs["startTime"]),
            "forecast_mw": pairs["forecast"],
            "actual_mw": pairs["actual"],
            "error_mw": pairs["error"],
            "publish_time": iso(pairs["publishTime"]).where(pairs["publishTime"].notna(), None),
            "lead_hours": pairs["lead_hours"],
        }
    )
    out = out.astype(object).where(out.notna(), None)
    for col in ("forecast_mw", "actual_mw", "error_mw", "lead_hours"):
        out[col] = out[col].map(_num)
    return out.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Accuracy vs forecast horizon
# ---------------------------------------------------------------------------
def horizon_sweep(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    start_day: date,
    end_day: date,
    max_hours: int = config.MAX_HORIZON_HOURS,
    step_hours: int = 1,
) -> list[dict]:
    """Accuracy metrics for h = 0, 1, 2 ... max_hours."""
    grid = target_grid(start_day, end_day)
    in_range = forecasts[forecasts["startTime"].isin(grid["startTime"])]  # filter once, reuse for every h
    rows = []
    for h in range(0, max_hours + 1, step_hours):
        pairs = horizon_pairs(actuals, in_range, h, start_day, end_day, prefiltered=True)
        m = compute_metrics(pairs)
        valid = pairs.dropna(subset=["lead_hours"])
        rows.append(
            {
                "horizon_hours": h,
                "n": m["n"],
                "mae_mw": m["mae_mw"],
                "rmse_mw": m["rmse_mw"],
                "bias_mw": m["bias_mw"],
                "wmape_pct": m["wmape_pct"],
                "abs_error_p90_mw": m["abs_error_p90_mw"],
                "median_actual_lead_hours": _num(valid["lead_hours"].median()) if not valid.empty else None,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Day-ahead decision view
# ---------------------------------------------------------------------------
def empirical_band(history: pd.DataFrame) -> tuple[float, float] | None:
    """P10 / P90 of (actual - forecast) from earlier days. None if not enough history."""
    valid = history.dropna(subset=["error"])
    if len(valid) < config.MIN_POINTS_FOR_BAND:
        return None
    residual = -valid["error"]
    return float(residual.quantile(0.1)), float(residual.quantile(0.9))


def delivery_day_view(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    delivery_day: date,
    days_before: int,
    decision_time: str,
) -> dict:
    """Everything the buyer needs to see for ONE delivery day."""
    start_day = date.fromisoformat(config.DELIVERY_START)
    end_day = date.fromisoformat(config.DELIVERY_END)
    pairs = decision_pairs(actuals, forecasts, start_day, end_day, days_before, decision_time)

    day = pairs[pairs["local_date"] == delivery_day].copy()

    # Error band built ONLY from days whose outcome was already known at decision time
    # (so we never "peek into the future"). With a D-1 decision, that means <= D-2.
    known_until = delivery_day - timedelta(days=days_before + 1)
    history = pairs[pairs["local_date"] <= known_until]
    band = empirical_band(history)
    if band:
        day["band_low_mw"] = (day["forecast"] + band[0]).clip(lower=0)
        day["band_high_mw"] = day["forecast"] + band[1]
    else:
        day["band_low_mw"] = np.nan
        day["band_high_mw"] = np.nan

    rows = series_rows(day)
    for r, lo, hi in zip(rows, day["band_low_mw"], day["band_high_mw"]):
        r["band_low_mw"] = _num(lo)
        r["band_high_mw"] = _num(hi)

    have_fc = day.dropna(subset=["forecast"])
    have_actual = day.dropna(subset=["actual"])
    peak = have_fc.loc[have_fc["forecast"].idxmax()] if not have_fc.empty else None
    trough = have_fc.loc[have_fc["forecast"].idxmin()] if not have_fc.empty else None

    vintages = []
    if not have_fc.empty:
        for pub, grp in have_fc.groupby("publishTime"):
            vintages.append(
                {
                    "publish_time": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "n_periods": int(len(grp)),
                    "first_period": grp["startTime"].min().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "last_period": grp["startTime"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )

    cutoff = day["cutoff"].dropna().iloc[0] if day["cutoff"].notna().any() else None
    return {
        "delivery_date": delivery_day.isoformat(),
        "decision_time_local": decision_time,
        "days_before": days_before,
        "cutoff_utc": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ") if cutoff is not None else None,
        "periods": rows,
        "summary": {
            "n_periods": int(len(day)),
            "n_with_forecast": int(len(have_fc)),
            "n_with_actual": int(len(have_actual)),
            "forecast_energy_mwh": _num(have_fc["forecast"].sum() * HALF_HOUR_MWH_FACTOR) if not have_fc.empty else None,
            "actual_energy_mwh": _num(have_actual["actual"].sum() * HALF_HOUR_MWH_FACTOR) if not have_actual.empty else None,
            "peak_forecast_mw": _num(peak["forecast"]) if peak is not None else None,
            "peak_forecast_time": peak["startTime"].strftime("%Y-%m-%dT%H:%M:%SZ") if peak is not None else None,
            "min_forecast_mw": _num(trough["forecast"]) if trough is not None else None,
            "min_forecast_time": trough["startTime"].strftime("%Y-%m-%dT%H:%M:%SZ") if trough is not None else None,
            "newest_forecast_published": vintages[-1]["publish_time"] if vintages else None,
            "oldest_forecast_published": vintages[0]["publish_time"] if vintages else None,
            "min_lead_hours": _num(have_fc["lead_hours"].min()) if not have_fc.empty else None,
            "max_lead_hours": _num(have_fc["lead_hours"].max()) if not have_fc.empty else None,
        },
        "vintages": vintages,
        "band": {
            "available": band is not None,
            "basis": f"{len(history.dropna(subset=['error']))} half-hours of earlier decisions" if band else "needs at least 2 earlier delivery days",
            "p10_residual_mw": _num(band[0]) if band else None,
            "p90_residual_mw": _num(band[1]) if band else None,
        },
        "metrics": compute_metrics(day),
    }


# ---------------------------------------------------------------------------
# Accuracy of the day-ahead decision rule across the whole month
# ---------------------------------------------------------------------------
def day_ahead_accuracy(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    start_day: date,
    end_day: date,
    days_before: int,
    decision_time: str,
) -> dict:
    pairs = decision_pairs(actuals, forecasts, start_day, end_day, days_before, decision_time)
    daily = []
    for d, grp in pairs.groupby("local_date"):
        m = compute_metrics(grp)
        daily.append(
            {
                "date": d.isoformat(),
                "n": m["n"],
                "mae_mw": m["mae_mw"],
                "rmse_mw": m["rmse_mw"],
                "bias_mw": m["bias_mw"],
                "wmape_pct": m["wmape_pct"],
                "mean_actual_mw": m["mean_actual_mw"],
                "mean_lead_hours": _num(grp["lead_hours"].mean()),
            }
        )
    lead = pairs["lead_hours"].dropna()
    return {
        "decision_time_local": decision_time,
        "days_before": days_before,
        "overall": compute_metrics(pairs),
        "lead_hours": {
            "min": _num(lead.min()) if not lead.empty else None,
            "median": _num(lead.median()) if not lead.empty else None,
            "max": _num(lead.max()) if not lead.empty else None,
        },
        "daily": daily,
        "histogram": error_histogram(pairs),
        "by_hour": error_by_hour(pairs),
        "by_level": error_by_level(pairs),
    }


def parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
