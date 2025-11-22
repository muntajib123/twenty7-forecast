# backend/src/trainer.py
import math
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from .data_io import load_training_csv
from .model import save_artifacts  # implemented below

# Kp is 0..9 → range^2 for normalized MSE
_KP_RANGE_SQ = 9.0 ** 2  # 81.0


def _make_xgb():
    return XGBRegressor(
        n_estimators=700,
        learning_rate=0.03,
        max_depth=5,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.5,
        random_state=42,
        tree_method="hist",
        n_jobs=0,
    )


def _json_safe(value):
    if value is None:
        return None
    try:
        vf = float(value)
        if math.isnan(vf) or math.isinf(vf):
            return None
        return vf
    except Exception:
        return None


def _normalized_mse(y_true, y_pred):
    raw_mse = mean_squared_error(y_true, y_pred)
    return raw_mse / _KP_RANGE_SQ, raw_mse, math.sqrt(raw_mse)


def train_and_eval(data_path: str, model_path: str, scaler_path: str):
    """
    - Loads training CSV via your data_io.load_training_csv (expected to return
      X (DataFrame), y (DataFrame or 2D array for 27-day targets), feature_cols, target_cols)
    - Fits a StandardScaler on X (features).
    - Trains a MultiOutputRegressor that predicts the full 27-day horizon in one call
      (shape (n_samples, 27) targets).
    - Saves model+scaler through save_artifacts(model, scaler, model_path, scaler_path).
    """
    X, y, feature_cols, target_cols = load_training_csv(data_path)

    if isinstance(y, pd.DataFrame):
        y_arr = y.values
    else:
        y_arr = np.asarray(y)

    n = len(X)

    # Defensive: clip targets to valid Kp range IF this is Kp training
    try:
        y_clip = np.clip(y_arr, 0.0, 9.0)
    except Exception:
        y_clip = y_arr

    # Standardize features
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.values.astype(np.float64))

    # Choose base estimator
    small_data = n < 60
    base = Ridge(alpha=1.0, random_state=42) if small_data else _make_xgb()
    model = MultiOutputRegressor(base)

    # Cross-validation diagnostics
    cv_mse_norm = cv_mse_raw = cv_rmse_raw = None
    if n >= 10:
        k = min(5, max(2, n // 10))
        kf = KFold(n_splits=k, shuffle=True, random_state=42)

        mses_norm = []
        mses_raw = []
        rmses_raw = []

        for tr_idx, va_idx in kf.split(Xs):
            X_tr, X_va = Xs[tr_idx], Xs[va_idx]
            y_tr, y_va = y_clip[tr_idx], y_clip[va_idx]

            fold_est = MultiOutputRegressor(_make_xgb() if not small_data else Ridge(alpha=1.0, random_state=42))
            fold_est.fit(X_tr, y_tr)
            pred = fold_est.predict(X_va)

            mse_norm, mse_raw, rmse_raw = _normalized_mse(y_va, pred)
            mses_norm.append(mse_norm)
            mses_raw.append(mse_raw)
            rmses_raw.append(rmse_raw)

        cv_mse_norm = float(np.mean(mses_norm))
        cv_mse_raw = float(np.mean(mses_raw))
        cv_rmse_raw = float(np.mean(rmses_raw))

    # Final fit on ALL data
    model.fit(Xs, y_clip)
    # Save model + scaler (scaler stored as numpy dict with mean_/scale_/n_features)
    save_artifacts(model, scaler, model_path, scaler_path)

    return {
        "cv_mse": _json_safe(cv_mse_norm),
        "cv_mse_raw": _json_safe(cv_mse_raw),
        "cv_rmse_raw": _json_safe(cv_rmse_raw),
        "n_samples": int(n),
        "n_features": int(X.shape[1]),
        "n_targets": int(y_arr.shape[1]) if y_arr.ndim == 2 else 1,
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "model_type": "Ridge" if small_data else "XGBoost",
    }
