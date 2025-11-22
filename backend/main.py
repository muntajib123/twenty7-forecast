# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import app as api_app       # your main API endpoints
from src.scheduler import start_scheduler

# ---------------- NEW: import historical router ----------------
# Note: src.historical.py should expose a FastAPI APIRouter named `router`.
# This file is new (see earlier instruction) and will be included into api_app
# so that the historical endpoints live under /api/historical...
try:
    from src.historical import router as historical_router
    _HISTORICAL_AVAILABLE = True
except Exception:
    # Keep server resilient if the file hasn't been created yet.
    historical_router = None
    _HISTORICAL_AVAILABLE = False

# ---------------- Create main FastAPI app ----------------
app = FastAPI(title="27-Day Forecast Backend", version="1.0.0")

# ---------------- (Optional) CORS on parent app ----------------
# This helps if you ever add top-level endpoints on the parent app.
# You already have CORS in src.api, but adding here is harmless.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # set to ["*"] for quick local testing if you prefer
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Mount api_app ----------------
# IMPORTANT: mount at root so routes declared as "/api/..." inside src.api
# resolve to "/api/..." (not "/api/api/...").
# Before mounting, attach the historical router into api_app (so no change to mount)
if _HISTORICAL_AVAILABLE and historical_router is not None:
    try:
        api_app.include_router(historical_router)
        print("[main] historical router included into api_app at /api/historical")
    except Exception as e:
        print(f"[main] failed to include historical router: {e}")

app.mount("/", api_app)

# ---------------- Startup event ----------------
@app.on_event("startup")
async def _on_startup():
    """Start daily scheduler at startup."""
    try:
        start_scheduler()
        print("[startup] Scheduler started successfully.")
    except Exception as e:
        print(f"[startup] Scheduler failed to start: {e}")

# ---------------- Shutdown event ----------------
@app.on_event("shutdown")
async def _on_shutdown():
    """Clean shutdown of scheduler."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.schedulers.base import STATE_RUNNING

        sched = getattr(app.state, "scheduler", None)
        if sched and isinstance(sched, BackgroundScheduler) and sched.state == STATE_RUNNING:
            sched.shutdown(wait=False)
            print("[shutdown] Scheduler stopped cleanly.")
    except Exception as e:
        print(f"[shutdown] Scheduler cleanup failed: {e}")
