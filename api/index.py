"""Vercel entry point.

Vercel runs every file in /api as a serverless function and looks for an ASGI variable
called `app`. We simply re-export the FastAPI app from the backend package.
"""
import sys
from pathlib import Path

# Make `import backend` work no matter what the working directory is.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app  # noqa: E402,F401
