"""API smoke tests against synthetic data (written to a temp folder, never to backend/data)."""
import pytest
from fastapi.testclient import TestClient

from backend import config, data_store
from backend.scripts import make_sample_data


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    saved = (config.DATA_DIR, config.ACTUALS_FILE, config.FORECASTS_FILE, config.META_FILE)
    make_sample_data.main(out_dir=out)
    data_store.get_store.cache_clear()
    from backend.main import app

    yield TestClient(app)
    config.DATA_DIR, config.ACTUALS_FILE, config.FORECASTS_FILE, config.META_FILE = saved
    data_store.get_store.cache_clear()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_flags_synthetic(client):
    body = client.get("/api/meta").json()
    assert body["source"] == "synthetic"
    assert body["delivery_start"] == "2026-01-01"


def test_decision_view(client):
    r = client.get("/api/decision", params={"date": "2026-01-15", "decision_time": "09:00"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["periods"]) == 48
    assert body["cutoff_utc"] == "2026-01-14T09:00:00Z"
    # Every forecast used must have been published before the cutoff
    for v in body["vintages"]:
        assert v["publish_time"] <= body["cutoff_utc"]
    assert body["band"]["available"] is True
    assert body["metrics"]["n"] == 48


def test_first_days_have_no_band(client):
    body = client.get("/api/decision", params={"date": "2026-01-03"}).json()
    assert body["band"]["available"] is False


def test_day_ahead_accuracy(client):
    body = client.get("/api/accuracy/day-ahead").json()
    assert len(body["daily"]) == 31
    assert body["overall"]["mae_mw"] > 0
    assert 14 <= body["lead_hours"]["min"] <= body["lead_hours"]["max"] <= 40


def test_error_grows_with_horizon(client):
    rows = client.get("/api/accuracy/by-horizon", params={"step_hours": 12}).json()["rows"]
    maes = [r["mae_mw"] for r in rows]
    assert maes[-1] > maes[0]  # synthetic data is built so that longer lead = worse


def test_horizon_endpoint(client):
    body = client.get("/api/accuracy/horizon", params={"horizon_hours": 24}).json()
    assert len(body["series"]) == 31 * 48
    assert len(body["histogram"]) == 24


def test_validation(client):
    assert client.get("/api/decision", params={"date": "2025-12-01"}).status_code == 400
    assert client.get("/api/decision", params={"date": "2026-01-10", "decision_time": "9am"}).status_code == 422
    assert client.get("/api/accuracy/horizon", params={"horizon_hours": 999}).status_code == 422
