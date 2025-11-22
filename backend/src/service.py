import os
import math
from datetime import datetime
from typing import Optional, Dict, Any

from dotenv import load_dotenv, find_dotenv
from pymongo import MongoClient, DESCENDING

# =========================================================
# Load environment variables (safe for OneDrive setups)
# =========================================================
env_path = find_dotenv(filename="backend/.env", raise_error_if_not_found=False)
load_dotenv(env_path)
print(f"✅ Loaded environment from: {env_path or 'default system env'}")

# =========================================================
# MongoDB Configuration
# =========================================================
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "spaceweather")
MONGO_COLL_PRED = os.getenv("MONGO_COLL_PRED", "predictions_27day")
MONGO_COLL_RUNS = os.getenv("MONGO_COLL_RUNS", "prediction_runs")
MONGO_COLL_NOAA = os.getenv("MONGO_COLL_NOAA", "noaa_27day")  # ✅ NOAA collection
SAVE_TO_MONGO = os.getenv("SAVE_TO_MONGO", "false").lower() == "true"


def _json_safe(value):
    """Convert NaN/Inf to None and ensure float-serializable values."""
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


# =========================================================
# Store Class — manages Mongo + in-memory fallback
# =========================================================
class Store:
    """
    Handles in-memory caching + optional MongoDB saving of
    model predictions, NOAA forecasts, and training runs.
    """

    def __init__(self):
        self._latest_prediction: Optional[Dict[str, Any]] = None
        self._latest_noaa: Optional[Dict[str, Any]] = None
        self.client: Optional[MongoClient] = None
        self.collection_pred = None
        self.collection_runs = None
        self.collection_noaa = None  # ✅ NOAA collection reference

        if SAVE_TO_MONGO and MONGO_URI:
            try:
                self.client = MongoClient(MONGO_URI)
                db = self.client[MONGO_DB]
                self.collection_pred = db[MONGO_COLL_PRED]
                self.collection_runs = db[MONGO_COLL_RUNS]
                self.collection_noaa = db[MONGO_COLL_NOAA]
                print(f"✅ Connected to MongoDB → {MONGO_DB} "
                      f"[{MONGO_COLL_PRED}, {MONGO_COLL_RUNS}, {MONGO_COLL_NOAA}]")
            except Exception as e:
                print(f"⚠️  Mongo connection failed: {e}. Running without persistence.")
                self.client = None
        else:
            if not SAVE_TO_MONGO:
                print("ℹ️  SAVE_TO_MONGO=false; skipping Mongo persistence.")
            elif not MONGO_URI:
                print("⚠️  MONGO_URI missing; running without DB persistence.")

    # =========================================================
    # ---------- PREDICTIONS (MODEL OUTPUT) ----------
    # =========================================================
    def save_predictions(self, meta: Dict[str, Any], horizon):
        """Save model predictions to memory and optionally MongoDB."""
        # Accept either a dict or None for meta
        meta = meta or {}

        doc = {
            "generated_at_utc": datetime.utcnow(),
            "source": meta.get("source", "api"),
            "predictions": horizon,
            "features_meta": meta.get("features_meta"),
            # new: normalized MSE (0..1) if caller computed it and passed it in meta
            "mse": _json_safe(meta.get("mse")) if "mse" in meta else None,
        }

        # Keep in memory
        self._latest_prediction = doc

        # Save to Mongo if available
        if self.collection_pred is not None:
            try:
                self.collection_pred.insert_one(doc)
                print("✅ Saved predictions to MongoDB.")
            except Exception as e:
                print(f"⚠️  Failed to save predictions to Mongo: {e}")
        else:
            print("ℹ️  Predictions saved only in memory (no MongoDB).")

    def get_latest_prediction(self) -> Optional[Dict[str, Any]]:
        """Return the most recent model prediction."""
        if self.collection_pred is not None:
            try:
                doc = self.collection_pred.find_one(sort=[("generated_at_utc", DESCENDING)])
                if doc:
                    doc["_id"] = str(doc["_id"])
                return doc
            except Exception as e:
                print(f"⚠️  Failed to fetch latest prediction from Mongo: {e}")
        return self._latest_prediction

    # =========================================================
    # ---------- TRAINING RUN LOGS ----------
    # =========================================================
    def save_run(self, meta: Dict[str, Any]):
        """Log training runs (in Mongo if enabled)."""
        meta = {**meta, "timestamp_utc": datetime.utcnow()}
        if self.collection_runs is not None:
            try:
                self.collection_runs.insert_one(meta)
                print("✅ Saved training run metadata to MongoDB.")
            except Exception as e:
                print(f"⚠️  Failed to save training run to Mongo: {e}")
        else:
            print("ℹ️  Training run logged in memory only:", meta)

    # =========================================================
    # ---------- NOAA 27-DAY FORECAST ----------
    # =========================================================
    def save_noaa_27day(self, data: Dict[str, Any]):
        """
        Save NOAA 27-day forecast (parsed JSON) to MongoDB or in-memory cache.
        """
        doc = {
            "saved_at_utc": datetime.utcnow(),
            "source": data.get("source", "NOAA 27-day outlook"),
            "issued_utc": data.get("issued_utc"),
            "start_date_utc": data.get("start_date_utc"),
            "days": data.get("days", []),
            "raw": data.get("raw", None),
        }

        # Keep in memory
        self._latest_noaa = doc

        # Save to MongoDB
        if self.collection_noaa is not None:
            try:
                self.collection_noaa.insert_one(doc)
                print("✅ Saved NOAA 27-day forecast to MongoDB.")
            except Exception as e:
                print(f"⚠️  Failed to save NOAA 27-day forecast to Mongo: {e}")
        else:
            print("ℹ️  NOAA forecast saved only in memory (no MongoDB).")

    def get_latest_noaa_27day(self) -> Optional[Dict[str, Any]]:
        """Return the most recent NOAA 27-day forecast."""
        if self.collection_noaa is not None:
            try:
                doc = self.collection_noaa.find_one(sort=[("saved_at_utc", DESCENDING)])
                if doc:
                    doc["_id"] = str(doc["_id"])
                return doc
            except Exception as e:
                print(f"⚠️  Failed to fetch latest NOAA forecast from Mongo: {e}")
        return self._latest_noaa
