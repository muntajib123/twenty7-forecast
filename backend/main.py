# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import app as api_app       # your main API endpoints
from src.scheduler import start_scheduler

# -------------------------------------------------------------
# NEW: Health Check Endpoint for UptimeRobot (ALWAYS returns 200)
# -------------------------------------------------------------
@api_app.get("/api/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}

# ---------------- NEW: import historical router ----------------
try:
    from src.historical import router as historical_router
    _HISTORICAL_AVAILABLE = True
except Exception:
    historical_router = None
    _HISTORICAL_AVAILABLE = False

app = FastAPI(title="27-Day Forecast Backend", version="1.0.0")

# ---------------- Configure CORS origins from env ----------------
# Provide BACKEND_ALLOWED_ORIGINS as a comma-separated list in Render (or set to "*" for quick debug)
allowed = os.environ.get("BACKEND_ALLOWED_ORIGINS", "").strip()
if allowed:
    allowed_origins = [o.strip() for o in allowed.split(",") if o.strip()]
else:
    # sensible defaults for local dev + common deployed URLs — update these to your real domains
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://twenty7-forecast.vercel.app",
        "https://twenty7-forecast.onrender.com",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Mount api_app (and include historical router) ----------------
if _HISTORICAL_AVAILABLE and historical_router is not None:
    try:
        api_app.include_router(historical_router)
        print("[main] historical router included into api_app at /api/historical")
    except Exception as e:
        print(f"[main] failed to include historical router: {e}")

app.mount("/", api_app)

# ---------------- Startup / Shutdown events ----------------
@app.on_event("startup")
async def _on_startup():
    try:
        start_scheduler()
        print("[startup] Scheduler started successfully.")
    except Exception as e:
        print(f"[startup] Scheduler failed to start: {e}")

@app.on_event("shutdown")
async def _on_shutdown():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.schedulers.base import STATE_RUNNING

        sched = getattr(app.state, "scheduler", None)
        if sched and isinstance(sched, BackgroundScheduler) and sched.state == STATE_RUNNING:
            sched.shutdown(wait=False)
            print("[shutdown] Scheduler stopped cleanly.")
    except Exception as e:
        print(f"[shutdown] Scheduler cleanup failed: {e}")
