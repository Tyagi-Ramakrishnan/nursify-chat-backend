# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python FastAPI backend for Nursify Aesthetics & Wellness. Deployed on Railway via Nixpacks. Three main modules run as a single FastAPI app:

- **`chat.py`** — app entrypoint; mounts the other routers, runs the scheduler on startup, and exposes `POST /api/v1/chat` (calls Claude Haiku with a hardcoded system prompt)
- **`intel.py`** — competitor intelligence module; scrapes Albuquerque med spa competitors weekly, stores results in SQLite (`/app/intel.db`), emails a weekly HTML briefing + instant alerts via Gmail SMTP, and exposes an `APIRouter` at `/intel`
- **`upload_result.py`** — photo management module; stores images in Cloudflare R2 and metadata in Postgres, exposes an `APIRouter` at `/upload` including a self-contained admin UI at `/upload/admin`

## Running locally

```bash
pip install -r requirements.txt

# Required env vars
export ANTHROPIC_API_KEY=...
export DATABASE_URL=...          # Railway Postgres connection string
export R2_SECRET_ACCESS_KEY=...  # Cloudflare R2
export GMAIL_APP_PASSWORD=...    # Gmail SMTP app password
export UPLOAD_SECRET=...         # Password for photo upload/admin endpoints

uvicorn chat:app --reload --port 8000
```

Health checks: `GET /health`, `GET /intel/health`, `GET /upload/health`

## Key architectural decisions

- **No test suite** — no `pytest`, no test files. Manual testing via the health endpoints and curl.
- **No linter config** — no `pyproject.toml`, `setup.cfg`, or `.flake8`. Run `python -m py_compile chat.py intel.py upload_result.py` to catch syntax errors.
- The scheduler (`APScheduler`) starts on FastAPI startup and runs `run_full_scan()` every Monday at 14:00 UTC (8am MT). Trigger it manually via `POST /intel/scan`.
- SQLite (`/app/intel.db`) is used for competitor intel only — ephemeral on Railway unless a persistent volume is mounted at `/app`. Postgres is used for photos.
- Upload auth is a single shared secret (`UPLOAD_SECRET`) passed as a form field or query param — not bearer tokens.
- Thumbnail resizing results are cached in-process with `functools.lru_cache(maxsize=500)` — cache is lost on restart.
- `PROCEDURE_ALIASES` in `upload_result.py` maps `"fillers"` → `["fillers", "lip-filler"]` so both slugs are returned when querying the `fillers` category.

## Deployment

Railway reads `railway.json` — start command is `uvicorn chat:app --host 0.0.0.0 --port $PORT`. All secrets are Railway environment variables. R2 account ID and access key ID are also hardcoded as fallback defaults in `upload_result.py` (the secret key is not).
