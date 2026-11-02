"""Unit tests for the analysis logic, using tiny hand-made data whose answers we can verify by eye."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend import analysis
from backend.analysis import to_utc

TARGET = "2026-01-02T12:00:00Z"


def make_forecasts(rows):
    df = pd.DataFrame(rows, columns=["publishTime", "startTime", "forecast"])
    df["publishTime"] = to_utc(df["publishTime"])
    df["startTime"] = to_utc(df["startTime"])
    return df


def make_actuals(rows):
    df = pd.DataFrame(rows, columns=["startTime", "actual"])
    df["startTime"] = to_utc(df["startTime"])
    return df


@pytest.fixture
def forecasts():
    # Three versions of the forecast for the same half hour
    return make_forecasts(
        [
            ("2026-01-01T06:00:00Z", TARGET, 100.0),
            ("2026-01-01T10:00:00Z", TARGET, 200.0),
            ("2026-01-01T15:00:00Z", TARGET, 300.0),
            ("2026-01-02T11:00:00Z", TARGET, 900.0),  # published only 1h before delivery
        ]
    )


@pytest.fixture
def actuals():
    return make_actuals([(TARGET, 250.0)])


def test_decision_cutoff_is_day_before_at_given_time():
    s = to_utc(pd.Series(["2026-01-02T00:30:00Z", "2026-01-02T23:30:00Z"]))
    cutoffs = analysis.decision_cutoffs(s, days_before=1, decision_time="09:00")
    assert list(cutoffs.dt.strftime("%Y-%m-%dT%H:%M")) == ["2026-01-01T09:00", "2026-01-01T09:00"]


def test_decision_rule_uses_latest_forecast_before_cutoff(forecasts, actuals):
    d = date(2026, 1, 2)
    p = analysis.decision_pairs(actuals, forecasts, d, d, days_before=1, decision_time="09:00")
    row = p[p["startTime"] == pd.Timestamp(TARGET)].iloc[0]
    assert row["forecast"] == 100.0  # 06:00 is the newest forecast that existed at 09:00
    assert row["actual"] == 250.0
    assert row["error"] == -150.0  # under-forecast
    assert row["lead_hours"] == pytest.approx(30.0)


def test_later_cutoff_picks_newer_forecast(forecasts, actuals):
    d = date(2026, 1, 2)
    p = analysis.decision_pairs(actuals, forecasts, d, d, days_before=1, decision_time="12:00")
    assert p[p["startTime"] == pd.Timestamp(TARGET)].iloc[0]["forecast"] == 200.0


def test_no_look_ahead_forecast_published_after_cutoff_never_used(forecasts, actuals):
    d = date(2026, 1, 2)
    for hhmm in ("00:00", "09:00", "14:59", "23:59"):
        p = analysis.decision_pairs(actuals, forecasts, d, d, 1, hhmm)
        used = p.dropna(subset=["publishTime"])
        assert (used["publishTime"] <= used["cutoff"]).all()


def test_horizon_rule(forecasts, actuals):
    d = date(2026, 1, 2)
    # >=24h before 12:00 => cutoff 2026-01-01 12:00 => picks the 10:00 forecast
    p24 = analysis.horizon_pairs(actuals, forecasts, 24, d, d)
    assert p24[p24["startTime"] == pd.Timestamp(TARGET)].iloc[0]["forecast"] == 200.0
    # >=20h => cutoff 16:00 => picks 15:00
    p20 = analysis.horizon_pairs(actuals, forecasts, 20, d, d)
    assert p20[p20["startTime"] == pd.Timestamp(TARGET)].iloc[0]["forecast"] == 300.0
    # >=0h => the newest one, published 11:00 on the day
    p0 = analysis.horizon_pairs(actuals, forecasts, 0, d, d)
    assert p0[p0["startTime"] == pd.Timestamp(TARGET)].iloc[0]["forecast"] == 900.0


def test_missing_forecast_is_nan_not_error(actuals):
    empty = make_forecasts([("2026-01-02T11:00:00Z", TARGET, 1.0)])
    d = date(2026, 1, 2)
    p = analysis.decision_pairs(actuals, empty, d, d, 1, "09:00")
    assert p["forecast"].isna().all()  # nothing was published before the cutoff
    m = analysis.compute_metrics(p)
    assert m["n"] == 0 and m["mae_mw"] is None


def test_metrics_values():
    pairs = pd.DataFrame(
        {
            "forecast": [110.0, 90.0, 150.0, 50.0],
            "actual": [100.0, 100.0, 100.0, 100.0],
        }
    )
    pairs["error"] = pairs["forecast"] - pairs["actual"]  # +10, -10, +50, -50
    pairs["abs_error"] = pairs["error"].abs()
    m = analysis.compute_metrics(pairs)
    assert m["n"] == 4
    assert m["mae_mw"] == 30.0
    assert m["bias_mw"] == 0.0
    assert m["rmse_mw"] == pytest.approx(np.sqrt((100 + 100 + 2500 + 2500) / 4), abs=1e-2)
    assert m["wmape_pct"] == pytest.approx(30.0)
    assert m["max_over_mw"] == 50.0 and m["max_under_mw"] == -50.0


def test_target_grid_has_48_periods_per_day():
    g = analysis.target_grid(date(2026, 1, 5), date(2026, 1, 6))
    assert len(g) == 96
    assert g["startTime"].iloc[0] == pd.Timestamp("2026-01-05T00:00:00Z")
    assert g["startTime"].iloc[-1] == pd.Timestamp("2026-01-06T23:30:00Z")


def test_parse_hhmm_rejects_garbage():
    with pytest.raises(ValueError):
        analysis.parse_hhmm("9am")
