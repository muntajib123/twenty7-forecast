# backend/src/config.py
from pathlib import Path

# Project root: .../twenty7-forecast
BASE_DIR = Path(__file__).resolve().parents[2]

BACKEND_DIR = BASE_DIR / "backend"
DATA_DIR    = BACKEND_DIR / "data"
MODEL_DIR   = BACKEND_DIR / "models"

# Files
DATA_PATH           = DATA_DIR / "training.csv"
FEATURES_TODAY_PATH = DATA_DIR / "features_today.csv"
MODEL_FILE          = MODEL_DIR / "model.pkl"
SCALER_FILE         = MODEL_DIR / "scaler.pkl"

# Ensure dirs exist (safe to import everywhere)
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
