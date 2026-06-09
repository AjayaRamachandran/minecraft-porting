"""Vercel Python serverless entry point.

Vercel picks up `app` from this file and routes /api/* here.
The actual FastAPI app lives in web/backend/server.py so the
same code runs both locally (uvicorn) and on Vercel.
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `web.backend.server` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.backend.server import app  # noqa: F401, E402 — re-exported for Vercel
