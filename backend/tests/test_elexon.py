"""Tests for the Elexon client using fake HTTP responses (no network needed)."""
from datetime import date, timedelta

import pytest

from backend import elexon


def fake_fuelhh(start: date, end: date):
    rows = []
    d = start
    while d <= end:
        for k in range(48):
            h, m = divmod(k * 30, 60)
            rows.append({"fuelType": "WIND", "startTime": f"{d.isoformat()}T{h:02d}:{m:02d}:00Z", "generation": 1000 + k})
            rows.append({"fuelType": "CCGT", "startTime": f"{d.isoformat()}T{h:02d}:{m:02d}:00Z", "generation": 5})
        d += timedelta(days=1)
    return rows


def test_actuals_keep_only_wind_and_dedupe(monkeypatch):
    s, e = date(2026, 1, 1), date(2026, 1, 3)
    monkeypatch.setattr(elexon, "_get_json", lambda client, url, params: fake_fuelhh(s, e))
    df = elexon.fetch_wind_actuals(s, e)
    assert len(df) == 3 * 48
    assert df["generation"].min() >= 1000  # CCGT rows (5 MW) were dropped


def test_actuals_fail_loudly_when_elexon_ignores_dates(monkeypatch):
    # Elexon returns the *latest* day instead of January -> we must not silently accept that.
    monkeypatch.setattr(elexon, "_get_json", lambda client, url, params: fake_fuelhh(date(2026, 10, 30), date(2026, 10, 30)))
    with pytest.raises(RuntimeError, match="ignored the date parameters"):
        elexon.fetch_wind_actuals(date(2026, 1, 1), date(2026, 1, 7))


def test_forecasts_fail_loudly_when_only_latest_vintage_returned(monkeypatch):
    rows = [{"publishTime": "2026-10-30T07:30:00Z", "startTime": "2026-10-30T12:00:00Z", "generation": 1.0}]
    monkeypatch.setattr(elexon, "_get_json", lambda client, url, params: rows)
    with pytest.raises(RuntimeError):
        elexon.fetch_wind_forecasts(date(2026, 1, 1), date(2026, 1, 5))


def test_chunking_covers_range_without_gaps():
    chunks = list(elexon._chunks(date(2026, 1, 1), date(2026, 1, 10), days=4))
    assert chunks == [(date(2026, 1, 1), date(2026, 1, 4)), (date(2026, 1, 5), date(2026, 1, 8)), (date(2026, 1, 9), date(2026, 1, 10))]
