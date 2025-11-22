# backend/src/model.py
import os
import joblib
from datetime import datetime

def save_artifacts(model, scaler, model_path: str, scaler_path: str):
    """
    Save trained model and scaler safely with overwrite protection.
    """
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    os.makedirs(os.path.dirname(scaler_path), exist_ok=True)

    meta = {
        "saved_utc": datetime.utcnow().isoformat() + "Z",
        "model_type": type(model).__name__,
        "scaler_type": type(scaler).__name__,
    }

    try:
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)
        print(f"[model] Saved model → {model_path}")
        print(f"[model] Saved scaler → {scaler_path}")
        print(f"[model] Metadata: {meta}")
    except Exception as e:
        print(f"[model] Failed to save artifacts: {e}")
        raise


def load_artifacts(model_path: str, scaler_path: str):
    """
    Load model and scaler; raise helpful errors if missing.
    Returns (scaler, model).
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file missing: {model_path}")
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"Scaler file missing: {scaler_path}")

    try:
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        print(f"[model] Loaded model from {model_path}")
        print(f"[model] Loaded scaler from {scaler_path}")
        return scaler, model
    except Exception as e:
        print(f"[model] Error loading artifacts: {e}")
        raise
