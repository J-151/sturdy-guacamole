"""Container start-up script (used by backend/Dockerfile).

1. If the data snapshot is missing, download it from Elexon (first start only; takes ~1-3 minutes).
2. Start the API server.

Written in Python rather than a shell script so it behaves identically on Windows, macOS and Linux.
"""
from __future__ import annotations

import os

import uvicorn

from backend import config


def main() -> None:
    if not (config.ACTUALS_FILE.exists() and config.FORECASTS_FILE.exists()):
        print("No data snapshot found in", config.DATA_DIR, "- downloading from Elexon (first start only)...", flush=True)
        from backend.scripts import fetch_data

        fetch_data.main()
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
