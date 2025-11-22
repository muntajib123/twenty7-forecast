# backend/src/scheduler.py
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import pandas as pd

from .trainer import train_and_eval
from .data_io import load_training_csv, load_features_csv
from .model import load_artifacts
from .config import DATA_PATH, FEATURES_TODAY_PATH, MODEL_FILE, SCALER_FILE
from .service import Store
from .features_today import rebuild_features_today  # ← build features_today.csv + append training row

# Optional: future forecast helper
try:
    from .feature_extend import build_extended_feature_row
    _HAS_BEYOND = True
except Exception:
    _HAS_BEYOND = False

# NOAA live fetcher
try:
    from .noaa import get_live_payload as fetch_noaa_27day
    _HAS_NOAA = True
except Exception:
    _HAS_NOAA = False

load_dotenv()
store = Store()


def _predict_from_df(model, scaler, df: pd.DataFrame, feature_cols):
    Xs = scaler.transform(df[feature_cols].values)
    return model.predict(Xs)[0].tolist()


def run_pipeline():
    """
    Daily pipeline:
      1) Train + validate model
      2) If MSE <= 1 → predict present (NOAA window)
      3) Predict future (BEYOND) if available
    """
    started = datetime.utcnow()
    print(f"[pipeline] start {started.isoformat()}Z")

    # ---- Step 0: make sure features_today.csv exists (built from latest NOAA)
    try:
        # Will raise if missing NOAA or any parse error
        _ = load_features_csv(FEATURES_TODAY_PATH, load_training_csv(DATA_PATH)[2])
    except Exception as e:
        print(f"[pipeline] features_today.csv missing/stale → rebuilding: {e}")
        try:
            rebuild_features_today(write_training=True)
        except Exception as e2:
            print(f"[pipeline] ❌ failed to rebuild features_today.csv: {e2}")
            finished = datetime.utcnow()
            return {
                "cv_mse": None,
                "saved_today": False,
                "saved_beyond": False,
                "started_utc": started.isoformat() + "Z",
                "finished_utc": finished.isoformat() + "Z",
                "note": "features_today.csv rebuild failed",
            }

    # ---- Step 1: Train model
    meta = train_and_eval(DATA_PATH, MODEL_FILE, SCALER_FILE)
    cv_mse = meta.get("cv_mse", None)
    store.save_run({"event": "daily_train", **meta})
    print(f"[pipeline] model trained | cv_mse={cv_mse}")

    # ---- Skip prediction if MSE too high
    if cv_mse is not None and cv_mse > 1:
        print("[pipeline] ❌ cv_mse too high (>1.0) — skipping predictions to keep last good model.")
        finished = datetime.utcnow()
        return {
            "cv_mse": cv_mse,
            "saved_today": False,
            "saved_beyond": False,
            "started_utc": started.isoformat() + "Z",
            "finished_utc": finished.isoformat() + "Z",
            "note": "MSE too high; model not used for prediction",
        }

    # ---- Step 2: Predict 27-day NOAA window
    X, _, feature_cols, _ = load_training_csv(DATA_PATH)
    features_df = load_features_csv(FEATURES_TODAY_PATH, feature_cols)
    scaler, model = load_artifacts(MODEL_FILE, SCALER_FILE)

    pred_today = _predict_from_df(model, scaler, features_df, feature_cols)
    store.save_predictions(
        {"source": "features_today.csv", "features_meta": features_df.iloc[0].to_dict()},
        pred_today,
    )
    print(f"[pipeline] ✅ Saved present 27-day forecast ({len(pred_today)} days)")

    saved_beyond = False

    # ---- Step 3: Predict 27 days beyond NOAA window
    if _HAS_BEYOND:
        try:
            base_row = features_df.iloc[0].to_dict()
            # If you want smoother/realistic, you can switch to mode="trend"
            ext_df = build_extended_feature_row(base_row, mode="mean7")

            # Remap d28..d54 → d1..d27
            remap = {
                f"f107_d{i}": ext_df[f"f107_d{27+i}"].values[0]
                for i in range(1, 28)
                if f"f107_d{27+i}" in ext_df.columns
            }
            remap.update({
                f"ap_d{i}": ext_df[f"ap_d{27+i}"].values[0]
                for i in range(1, 28)
                if f"ap_d{27+i}" in ext_df.columns
            })
            remap_df = pd.DataFrame([remap])[feature_cols]

            pred_beyond = _predict_from_df(model, scaler, remap_df, feature_cols)
            store.save_predictions(
                {
                    "source": "beyond(mode=mean7, offset_days=28)",
                    "features_meta": {"mode": "mean7", "offset_days": 28},
                },
                pred_beyond,
            )
            saved_beyond = True
            print(f"[pipeline] ✅ Saved future forecast ({len(pred_beyond)} days)")
        except Exception as e:
            print(f"[pipeline] ⚠️ BEYOND step skipped: {e}")
    else:
        print("[pipeline] ⚠️ BEYOND skipped: feature_extend.py not found")

    finished = datetime.utcnow()
    print(f"[pipeline] done {finished.isoformat()}Z")

    return {
        "cv_mse": cv_mse,
        "saved_today": True,
        "saved_beyond": saved_beyond,
        "started_utc": started.isoformat() + "Z",
        "finished_utc": finished.isoformat() + "Z",
    }


def sync_noaa_27day():
    """
    Fetch and save the latest NOAA 27-day outlook,
    then rebuild features_today.csv and append a training row.
    """
    if not _HAS_NOAA:
        msg = "noaa.py not available; cannot sync NOAA 27-day."
        print(f"[noaa] {msg}")
        return {"saved": False, "error": msg}

    try:
        data = fetch_noaa_27day()
        store.save_noaa_27day(data)
        print(f"[noaa] ✅ Saved {len(data.get('days', []))} days; issued={data.get('issued_utc')}")

        # ← Build features_today.csv + append into training.csv
        try:
            summary = rebuild_features_today(write_training=True)
            print(f"[features_today] ✅ {summary}")
        except Exception as e:
            print(f"[features_today] ⚠️ rebuild failed: {e}")

        return {"saved": True, "count": len(data.get('days', []))}
    except Exception as e:
        print(f"[noaa] ⚠️ Fetch/save failed: {e}")
        return {"saved": False, "error": str(e)}


def start_scheduler():
    """
    Start two daily jobs in UTC:
      - 00:35 → sync NOAA
      - 00:36 → run pipeline (train + predict)
    """
    tzname = os.getenv("CRON_TZ", "UTC")

    noaa_time = os.getenv("CRON_NOAA_TIME", "00:35")
    pipe_time = os.getenv("CRON_LOCAL_TIME", "00:36")

    hour_noaa, min_noaa = [int(x) for x in noaa_time.split(":")]
    hour_main, min_main = [int(x) for x in pipe_time.split(":")]

    sched = BackgroundScheduler(timezone=ZoneInfo(tzname))

    # NOAA sync (fetch + store)
    sched.add_job(
        sync_noaa_27day,
        "cron",
        hour=hour_noaa,
        minute=min_noaa,
        id="daily_noaa_sync",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        jitter=10,
    )

    # Main pipeline (train + predict)
    sched.add_job(
        run_pipeline,
        "cron",
        hour=hour_main,
        minute=min_main,
        id="daily27_pipeline",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        jitter=10,
    )

    sched.start()
    print(f"[scheduler] NOAA sync at {hour_noaa:02d}:{min_noaa:02d} {tzname}")
    print(f"[scheduler] Pipeline at {hour_main:02d}:{min_main:02d} {tzname}")
    return sched
