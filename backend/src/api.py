# backend/src/api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import math
import traceback
import numpy as np
from typing import Optional

from .config import (
    DATA_PATH,
    FEATURES_TODAY_PATH,
    MODEL_DIR,
    MODEL_FILE,
    SCALER_FILE,
)
from .trainer import train_and_eval
from .model import load_artifacts
from .data_io import load_training_csv, load_features_csv
from .service import Store
from .schemas import TrainResponse, PredictResponse, PostFeaturesRequest
from .features import dict_to_feature_df
from .scheduler import run_pipeline, sync_noaa_27day
from .features_today import rebuild_features_today
from .forecaster import generate_27day_forecast  # robust forecaster

# OPTIONAL: needed for /predict/beyond
try:
    from .feature_extend import build_extended_feature_row
    _HAS_BEYOND = True
except Exception:
    _HAS_BEYOND = False

# NOAA fetcher (optional)
try:
    from .noaa import get_live_payload as fetch_noaa_27day
    _HAS_NOAA = True
except Exception:
    _HAS_NOAA = False


app = FastAPI(title="27-Day Forecast API", version="1.4.1")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = Store()

# ---------------- Helpers ----------------
def _is_stale(path: str, minutes: int = 180) -> bool:
    p = Path(path)
    if not p.exists():
        return True
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return (datetime.now() - mtime) > timedelta(minutes=minutes)


def _unpack_loaded(loaded):
    """
    Accept either (scaler, model) or (model, scaler) and return (scaler, model).
    """
    if isinstance(loaded, tuple) and len(loaded) == 2:
        a, b = loaded
        # prefer to detect scaler by presence of .transform, model by .predict
        if hasattr(a, "transform") and hasattr(b, "predict"):
            return a, b
        if hasattr(b, "transform") and hasattr(a, "predict"):
            return b, a
        # fallback: assume (scaler, model)
        return a, b
    raise RuntimeError("load_artifacts returned unexpected object; expected a 2-tuple")


def _sanitize_list_of_numbers(arr):
    out = []
    for v in arr:
        try:
            vf = float(v)
            if math.isnan(vf) or math.isinf(vf):
                out.append(None)
            else:
                out.append(vf)
        except Exception:
            out.append(None)
    return out


def _clean_kp_series(kp_list):
    """
    Input: iterable of numbers or None
    Output: list of cleaned numbers (int when close to integer; else 3 decimals)
    """
    out = []
    for v in kp_list:
        try:
            if v is None:
                out.append(None)
                continue
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                out.append(None)
                continue
            # clip to physical KP range
            clipped = max(0.0, min(9.0, fv))
            nearest = round(clipped)
            # if within 0.02 of exact integer -> return integer
            if abs(clipped - nearest) < 0.02:
                out.append(int(nearest))
            else:
                out.append(round(float(clipped), 3))
        except Exception:
            out.append(None)
    return out


# ---------------- Utility: robust loader/predictor ----------------
def _predict_from_df(features_df: pd.DataFrame, feature_cols):
    """
    Robust wrapper around load_artifacts + scaler.transform + model.predict.

    Returns: list of sanitized floats (length = horizon).
    Raises HTTPException on failure.

    Sanitizes numeric results, clips into physical range [0,9], and applies user-friendly rounding:
      - if value is within 0.02 of an integer -> round to that integer
      - otherwise round to 3 decimal places
    None is used when the value is NaN or infinite.
    """
    try:
        if not os.path.exists(MODEL_FILE) or not os.path.exists(SCALER_FILE):
            raise HTTPException(status_code=400, detail="Model not trained yet.")

        loaded = load_artifacts(MODEL_FILE, SCALER_FILE)
        scaler_obj, model_obj = _unpack_loaded(loaded)

        # Debug prints (helpful in logs)
        print("[debug] _predict_from_df: model type:", type(model_obj))
        print("[debug] _predict_from_df: scaler type:", type(scaler_obj))
        print("[debug] _predict_from_df: features_df.shape:", features_df.shape)
        print("[debug] _predict_from_df: feature_cols len:", len(feature_cols))

        # ensure required feature columns exist
        for c in feature_cols:
            if c not in features_df.columns:
                raise HTTPException(status_code=400, detail=f"Missing feature column: {c}")

        Xvals = features_df[feature_cols].values.astype(float)
        print("[debug] Xvals sample:", Xvals[:1])

        # transform features
        Xs = scaler_obj.transform(Xvals)
        print("[debug] Xs.shape after scaler.transform:", Xs.shape)

        pred = model_obj.predict(Xs)
        # convert to numpy array
        try:
            pred = np.asarray(pred)
        except Exception:
            pred = __import__("numpy").array(pred)
        print("[debug] raw model.predict shape:", pred.shape)

        # Flatten sensible prediction into a 1D list
        if pred.ndim == 2 and pred.shape[0] >= 1:
            # If model returned (1, N) -> take [0]
            if pred.shape[0] == 1:
                out = pred[0].tolist()
            else:
                # If multiple rows predicted, choose first row
                out = pred[0].tolist()
        elif pred.ndim == 1:
            out = pred.tolist()
        else:
            # try to flatten sensibly
            out = pred.reshape(-1).tolist()

        # Sanitize numeric and apply user-friendly rounding/clipping:
        sanitized = []
        for i, v in enumerate(out):
            try:
                vf = float(v)
                if math.isnan(vf) or math.isinf(vf):
                    sanitized.append(None)
                    continue
                # Clip to physical KP range
                clipped = max(0.0, min(9.0, vf))
                # Round to integer if very close to integer
                nearest_int = round(clipped)
                if abs(clipped - nearest_int) < 0.02:
                    sanitized.append(int(nearest_int))
                else:
                    sanitized.append(round(float(clipped), 3))
            except Exception:
                sanitized.append(None)

        print("[debug] prediction (sanitized):", sanitized[:10])
        return sanitized

    except HTTPException:
        raise
    except Exception as e:
        print("[error] _predict_from_df failed:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"_predict_from_df failed: {str(e)}")


# ---------------- STARTUP ----------------
@app.on_event("startup")
def startup_bootstrap():
    os.makedirs(MODEL_DIR, exist_ok=True)


# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "API is running", "message": "Use /api/health or other endpoints"}


# ---------------- HEALTH ----------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------- TRAIN ----------------
@app.post("/api/train", response_model=TrainResponse)
def train():
    try:
        meta = train_and_eval(DATA_PATH, MODEL_FILE, SCALER_FILE)
        store.save_run({"event": "train", **meta})
        return meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- FEATURES: REBUILD ----------------
@app.post("/api/features/rebuild")
def features_rebuild():
    try:
        summary = rebuild_features_today(write_training=True)
        return {"status": "ok", **summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- PREDICT TODAY ----------------
@app.get("/api/predict/today", response_model=PredictResponse)
def predict_today():
    try:
        # If features stale, refresh NOAA/features and pipeline
        if _is_stale(FEATURES_TODAY_PATH, minutes=180):
            try:
                sync_noaa_27day()
            except Exception:
                pass
            try:
                rebuild_features_today(write_training=True)
            except Exception:
                pass
            run_pipeline()

        # Load features
        X, _, feature_cols, _ = load_training_csv(DATA_PATH)
        features_df = load_features_csv(FEATURES_TODAY_PATH, feature_cols)

        # Raw prediction from model
        h_raw = _predict_from_df(features_df, feature_cols)

        # Safe-normalize horizon: numeric floats or None
        horizon = _sanitize_list_of_numbers(h_raw)
        horizon = _clean_kp_series(horizon)

        # Compute normalized MSE vs NOAA forecast (if available)
        mse_norm_str = ""
        try:
            noaa = store.get_latest_noaa_27day()
            if noaa and isinstance(noaa.get("days"), list):
                noaa_kp = []
                for d in noaa["days"]:
                    try:
                        kpv = d.get("kp") if isinstance(d, dict) else None
                        noaa_kp.append(None if kpv is None else float(kpv))
                    except Exception:
                        noaa_kp.append(None)

                y_true = []
                y_pred = []
                n = min(len(noaa_kp), len(horizon))
                for i in range(n):
                    if (noaa_kp[i] is not None) and (horizon[i] is not None):
                        y_true.append(noaa_kp[i])
                        y_pred.append(horizon[i])

                if len(y_true) > 0:
                    from sklearn.metrics import mean_squared_error
                    raw = mean_squared_error(y_true, y_pred)
                    mse_norm = raw / (9.0 ** 2)  # normalize by 81
                    mse_norm_str = f"{float(mse_norm):.6f}"
        except Exception:
            mse_norm_str = ""

        meta = {
            "source": "features_today.csv",
            "features_meta": json.dumps(features_df.iloc[0].to_dict()),
            "generated_utc": datetime.utcnow().isoformat(),
            "features_mtime": datetime.fromtimestamp(Path(FEATURES_TODAY_PATH).stat().st_mtime).isoformat(),
            "mse": mse_norm_str,
        }

        store.save_predictions(meta, horizon)

        return {
            "horizon": horizon,
            "feature_row": features_df.iloc[0].to_dict(),
            "meta": meta,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- PREDICT WITH BODY ----------------
@app.post("/api/predict", response_model=PredictResponse)
def predict_with_body(req: PostFeaturesRequest):
    try:
        X, _, feature_cols, _ = load_training_csv(DATA_PATH)
        features_df = dict_to_feature_df(req.features, feature_cols)
        h_raw = _predict_from_df(features_df, feature_cols)

        horizon = _sanitize_list_of_numbers(h_raw)
        horizon = _clean_kp_series(horizon)

        meta = {
            "source": "POST",
            "generated_utc": datetime.utcnow().isoformat(),
        }

        store.save_predictions(meta, horizon)
        return {
            "horizon": horizon,
            "feature_row": features_df.iloc[0].to_dict(),
            "meta": meta,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- LATEST PREDICTION ----------------
@app.get("/api/predictions/latest")
def latest_saved_prediction():
    doc = store.get_latest_prediction()
    if not doc:
        raise HTTPException(status_code=404, detail="No prediction found.")
    return doc


# ---------------- NOAA: ALWAYS AVAILABLE ----------------
@app.get("/api/noaa/27day/latest")
def get_noaa_27day_latest():
    doc = store.get_latest_noaa_27day()
    if not doc:
        raise HTTPException(status_code=404, detail="No NOAA forecast found.")
    return doc


@app.get("/api/noaa/27day/live")
def get_noaa_27day_live():
    if _HAS_NOAA:
        try:
            return fetch_noaa_27day()
        except Exception:
            pass
    doc = store.get_latest_noaa_27day()
    if not doc:
        raise HTTPException(status_code=404, detail="No NOAA forecast available.")
    return doc


# ---------------- CRON MANUAL ----------------
@app.post("/api/cron/run-now")
def cron_run_now():
    try:
        sync_noaa_27day()
        summary = rebuild_features_today(write_training=True)
        out = run_pipeline()
        return {"status": "ok", "features": summary, "pipeline": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- helper: Kp -> Ap conversion ----------------
def _kp_to_ap_scalar(kp_val: Optional[float]) -> Optional[float]:
    """
    Convert a Kp (can be float) to an approximate daily Ap using a NOAA-like mapping.
    Implementation details:
     - For integer Kp 0..9 we use a standard representative ap baseline:
         ap_baseline = [0, 2, 4, 7, 12, 20, 39, 70, 120, 200]
       (commonly used in space-weather code as the canonical mapping).
     - For fractional Kp (e.g. 3.94) we perform linear interpolation between the two
       integer baselines. This matches the common approach of interpolating between
       discrete Kp steps (NOAA uses a discrete 28-step Kp scale; this gives a smooth
       continuous proxy).
     - Returns rounded value (3 decimals).
    """
    if kp_val is None:
        return None
    try:
        kv = float(kp_val)
    except Exception:
        return None
    if math.isnan(kv) or math.isinf(kv):
        return None
    kv = max(0.0, min(9.0, kv))
    # baseline ap mapping for integer Kp = 0..9 (widely-used representative mapping)
    ap_baseline = [0.0, 2.0, 4.0, 7.0, 12.0, 20.0, 39.0, 70.0, 120.0, 200.0]
    low = int(math.floor(kv))
    high = int(math.ceil(kv))
    if low == high:
        return round(float(ap_baseline[low]), 3)
    t = kv - low
    ap_val = ap_baseline[low] * (1 - t) + ap_baseline[high] * t
    return round(float(ap_val), 3)


# ---------------- PREDICT BEYOND ----------------
@app.get("/api/predict/beyond")
def predict_beyond(mode: str = "mean7", offset_days: int = 27):
    """
    Predict a 27-day Kp horizon beyond the available NOAA days using the model,
    and also return the corresponding Ap and F10.7 series produced by the
    feature extender so the frontend can display them.

    Rules applied:
     - use build_extended_feature_row to get deterministic f107/ap extents;
     - compute kp horizon using the model (as before);
     - recompute ap_horizon from kp_horizon using _kp_to_ap_scalar so AP is consistent with KP;
     - replace any f107_horizon values <= 115 (or missing/0) with deterministic plausible values in 120..138.
    """
    if not _HAS_BEYOND:
        raise HTTPException(status_code=400, detail="feature_extend.py missing.")
    try:
        # load training metadata / feature columns and today's features
        X, _, feature_cols, _ = load_training_csv(DATA_PATH)
        features_df = load_features_csv(FEATURES_TODAY_PATH, feature_cols)
        base_row = features_df.iloc[0].to_dict()

        # Build full 54-day extended feature DataFrame (f107_d1..f107_d54, ap_d1..ap_d54)
        ext_df = build_extended_feature_row(base_row, mode=mode)

        # Build ap_horizon and f107_horizon from days 28..54 (i.e. indices 27..53)
        ap_horizon = []
        f107_horizon = []
        for i in range(1, 28):
            fkey = f"f107_d{27 + i}"   # 28..54
            akey = f"ap_d{27 + i}"
            try:
                fval = ext_df[fkey].values[0]
            except Exception:
                fval = None
            try:
                aval = ext_df[akey].values[0]
            except Exception:
                aval = None

            try:
                f107_horizon.append(float(fval) if fval is not None else None)
            except Exception:
                f107_horizon.append(None)
            try:
                ap_horizon.append(float(aval) if aval is not None else None)
            except Exception:
                ap_horizon.append(None)

        # --- Build remap row for the model: f107_d1..f107_d27 and ap_d1..ap_d27 must match feature_cols
        remap = {}
        for i in range(1, 28):
            fkey_src = f"f107_d{i}"
            akey_src = f"ap_d{i}"
            try:
                fval_src = ext_df[fkey_src].values[0]
            except Exception:
                fval_src = None
            try:
                aval_src = ext_df[akey_src].values[0]
            except Exception:
                aval_src = None

            # fallback to 0.0 if missing (model expects numeric input), extension already tried to clean
            remap[f"f107_d{i}"] = float(fval_src) if fval_src is not None else 0.0
            remap[f"ap_d{i}"] = float(aval_src) if aval_src is not None else 0.0

        # Ensure remap matches feature_cols ordering
        remap_df = pd.DataFrame([remap]).reindex(columns=feature_cols, fill_value=0.0)

        raw_pred = _predict_from_df(remap_df, feature_cols)

        horizon = []
        for v in raw_pred:
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    hval = None
                else:
                    clipped = max(0.0, min(9.0, fv))
                    hval = round(float(clipped), 3)
                horizon.append(hval)
            except Exception:
                horizon.append(None)

        # If model returns fewer than 27 entries, pad with None
        if len(horizon) < 27:
            horizon = (horizon + [None] * 27)[:27]
        else:
            horizon = horizon[:27]

        # Fill missing horizon entries from ext_df where possible
        for idx in range(27):
            if horizon[idx] is None:
                kp_col_28 = f"kp_d{28 + idx}"
                kp_col_1 = f"kp_d{1 + idx}"
                try:
                    if kp_col_28 in ext_df.columns:
                        val = ext_df[kp_col_28].values[0]
                        horizon[idx] = round(float(val), 3) if val is not None else None
                    elif kp_col_1 in ext_df.columns:
                        val = ext_df[kp_col_1].values[0]
                        horizon[idx] = round(float(val), 3) if val is not None else None
                except Exception:
                    pass

        # If still missing, forward/backward fill using last known value or NOAA fallback
        last_known = None
        for v in horizon:
            if v is not None:
                last_known = v
                break
        if last_known is None:
            for v in reversed(horizon):
                if v is not None:
                    last_known = v
                    break
        for i in range(len(horizon)):
            if horizon[i] is None:
                if last_known is not None:
                    horizon[i] = last_known
                else:
                    try:
                        doc = store.get_latest_noaa_27day()
                        if doc and isinstance(doc.get("days"), list) and len(doc["days"]) >= 27:
                            val = doc["days"][i].get("kp_noaa") or doc["days"][i].get("kp")
                            if val is not None:
                                horizon[i] = round(float(val), 3)
                                continue
                    except Exception:
                        pass
                    horizon[i] = 0.0

        # Clean KP values formatting (integers when near-integer)
        horizon = _clean_kp_series(horizon)

        # --- recompute ap_horizon from kp horizon using NOAA-like conversion for consistency ---
        ap_horizon_from_kp = []
        for kpv in horizon:
            try:
                apv = _kp_to_ap_scalar(kpv)
                ap_horizon_from_kp.append(apv)
            except Exception:
                ap_horizon_from_kp.append(None)

        # Use AP from KP conversion instead of the ext_df-generated AP (keeps AP consistent with model KP)
        ap_horizon = ap_horizon_from_kp

        # --- Ensure f107_horizon values obey requested rule: if 0 or <=115 set to plausible 120..138 ---
        for idx in range(len(f107_horizon)):
            v = f107_horizon[idx]
            # If missing or <= 115, replace using a deterministic pseudo-random pattern so values vary
            if (v is None) or (not np.isfinite(float(v))) or (float(v) <= 115.0):
                # deterministic replacement to keep values varied but reproducible
                # pattern chosen to produce values in 120..138
                f107_horizon[idx] = float(120 + ((idx + 1) * 13 + 7) % 19)

        # Truncate/pad to length 27
        if len(ap_horizon) < 27:
            ap_horizon = (ap_horizon + [None] * 27)[:27]
        else:
            ap_horizon = ap_horizon[:27]
        if len(f107_horizon) < 27:
            f107_horizon = (f107_horizon + [None] * 27)[:27]
        else:
            f107_horizon = f107_horizon[:27]

        # Round numeric results
        ap_horizon = [round(x, 3) if (x is not None) else None for x in ap_horizon]
        f107_horizon = [round(x, 3) if (x is not None) else None for x in f107_horizon]

        # Compute dates
        try:
            doc = store.get_latest_noaa_27day()
            last_date = doc["days"][26]["date_utc"].replace("Z", "+00:00")
            start = datetime.fromisoformat(last_date).date() + timedelta(days=1)
        except Exception:
            start = datetime.utcnow().date() + timedelta(days=offset_days)

        dates = [(start + timedelta(days=i)).isoformat() for i in range(27)]

        return {
            "mode": mode,
            "offset_days": offset_days,
            "dates_utc": dates,
            "horizon": horizon,
            "ap_horizon": ap_horizon,
            "f107_horizon": f107_horizon,
            "meta": {"generated_utc": datetime.utcnow().isoformat()},
        }

    except HTTPException:
        raise
    except Exception as e:
        print("[predict_beyond] unexpected error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
