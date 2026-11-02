"""Central configuration. Everything tweakable lives here so reviewers can find it fast."""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# WIND_DATA_DIR lets you point the app at another folder (handy for tests and Docker volumes).
DATA_DIR = Path(os.environ.get("WIND_DATA_DIR", BASE_DIR / "data"))
ACTUALS_FILE = DATA_DIR / "actuals.csv"
FORECASTS_FILE = DATA_DIR / "forecasts.csv.gz"
META_FILE = DATA_DIR / "meta.json"

# ---------------------------------------------------------------------------
# Elexon BMRS (Insights Solution) API. No API key is required.
# ---------------------------------------------------------------------------
ELEXON_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
FUELHH_STREAM = f"{ELEXON_BASE_URL}/datasets/FUELHH/stream"
WINDFOR_STREAM = f"{ELEXON_BASE_URL}/datasets/WINDFOR/stream"

# ---------------------------------------------------------------------------
# Scope of the challenge: purchase decisions made for January 2026
# ---------------------------------------------------------------------------
# Delivery days we care about (inclusive). Elexon timestamps are UTC; in January
# the UK is on GMT (= UTC) so there are no daylight-saving shifts to worry about.
DELIVERY_START = "2026-01-01"
DELIVERY_END = "2026-01-31"

# Forecasts for 1 Jan are published on 31 Dec (or earlier), so we pull a little
# earlier than the delivery window to have the full history of forecast "vintages".
FORECAST_PUBLISH_FROM = "2025-12-25"
FORECAST_PUBLISH_TO = "2026-02-01"

# ---------------------------------------------------------------------------
# Day-ahead market assumptions
# ---------------------------------------------------------------------------
# Decisions for delivery day D are made on D-1. The GB day-ahead auctions close
# in the morning of D-1 (roughly 09:20-09:50 UK time). The user can change this
# in the UI; this is just the default (UK local clock time).
DEFAULT_DECISION_TIME = "09:00"
DEFAULT_DAYS_BEFORE = 1
LOCAL_TZ = "Europe/London"

# Forecast horizon explorer: how far ahead (hours) we let the user look.
MAX_HORIZON_HOURS = 48

# Minimum number of historical points before we trust an empirical error band.
MIN_POINTS_FOR_BAND = 96  # = 2 days of half-hours
