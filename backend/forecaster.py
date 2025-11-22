# backend/src/forecaster.py
"""
Safe forecaster for 27-day horizon.

Compatible with backend/src/model.py which exposes:
    save_artifacts(model, scaler, model_path, scaler_path)
    load_artifacts(model_path, scaler_path) -> (scaler, model)

This forecaster:
 - tries a one-shot prediction (model outputs all horizon days at once),
 - otherwise falls back to an iterative (recursive) prediction loop that
   updates the sliding buffer in *unscaled* space and re-scales it each step,
   ensuring the window changes and outputs are not identical each step.
 - has best-effort mapping to update feature columns named 'Ap', 'F107', 'Kp'
   when the model returns 1 or 2 target values per step. Adjust mapping if your
   outputs are ordered differently.
"""

from typing import List, Tuple
import numpy as np
import pandas as pd
import os

# import your current load_artifacts
from .model import load_artifacts

# Helper to coerce numeric arrays and replace NaNs/Infs
def _safe_numeric(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64)
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    return a

def _unpack_load_return(load_ret) -> Tuple[object, object]:
    """
    Your load_artifacts currently returns (scaler, model).
    But some code might expect (model, scaler). Accept both:
    - If first object has transform attribute it's probably scaler.
    - If second has transform it's scaler.
    Return (model, scaler).
    """
    if isinstance(load_ret, tuple) and len(load_ret) == 2:
        a, b = load_ret
        # heuristics: scaler has 'transform' attr (StandardScaler or joblib-saved scaler),
        # model typically has 'predict' but scaler also may have 'predict' rarely; prefer 'transform' test
        if hasattr(a, "transform") and hasattr(b, "predict"):
            return b, a
        if hasattr(b, "transform") and hasattr(a, "predict"):
            return a, b
        # fallback by attribute presence
        if hasattr(a, "predict") and hasattr(b, "transform"):
            return a, b
        if hasattr(b, "predict") and hasattr(a, "transform"):
            return b, a
    raise RuntimeError("Unexpected return from load_artifacts: expected (scaler, model) or (model, scaler).")

def generate_27day_forecast(history_df: pd.DataFrame,
                            model_path: str,
                            scaler_path: str,
                            feature_cols: List[str],
                            horizon: int = 27,
                            iterative_if_needed: bool = True) -> pd.DataFrame:
    """
    Generate a horizon-day forecast.

    Args:
      - history_df: DataFrame containing historical rows with columns including feature_cols.
                    Must have at least 1 row; more is better if you rely on history.
      - model_path / scaler_path: as used by backend/src/model.py
      - feature_cols: list of features in the same order used at training time.
      - horizon: number of days to forecast (default 27).
      - iterative_if_needed: if model doesn't return full horizon in one shot,
                             allow iterative recursion to produce horizon.

    Returns:
      - DataFrame with columns:
          'day' (1..horizon) and then either:
            - if single-target-per-step: columns ['pred_0', ...] (one or more preds per day),
            - if one-shot model: columns ['pred_d1','pred_d2',...,'pred_d{horizon}'] (single column per day).
    """
    if not isinstance(history_df, pd.DataFrame):
        raise ValueError("history_df must be a pandas DataFrame")

    # check presence of feature columns
    for c in feature_cols:
        if c not in history_df.columns:
            raise ValueError(f"Missing feature column in history: {c}")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        raise FileNotFoundError("model_path or scaler_path not found")

    # load artifacts using your load_artifacts
    loaded = load_artifacts(model_path, scaler_path)
    model, scaler = _unpack_load_return(loaded)

    # Ensure scaler has transform/inverse_transform; if not, raise helpful error
    if not hasattr(scaler, "transform"):
        raise RuntimeError("Loaded scaler does not support .transform(); ensure scaler was saved correctly.")

    # Build numeric history matrix (N_hist, n_features)
    X_hist = _safe_numeric(history_df[feature_cols].values)
    n_hist, n_features = X_hist.shape

    # Use last observed row as the input for one-shot path
    last_row = X_hist[-1:].astype(np.float64)  # shape (1, n_features)
    last_row_scaled = scaler.transform(last_row)

    # 1) Try one-shot: if model.predict(last_row_scaled) returns an array of shape (1, >=horizon)
    try:
        one_shot = model.predict(last_row_scaled)
        one_shot = np.asarray(one_shot)
        # case: model returns (1, horizon) or (n_samples, horizon)
        if one_shot.ndim == 2 and one_shot.shape[1] >= horizon:
            # Interpret as single-column-per-day forecast. Take first horizon columns.
            pred_row = one_shot[0, :horizon]
            cols = [f"pred_d{d+1}" for d in range(len(pred_row))]
            df = pd.DataFrame([pred_row], columns=cols)
            df.insert(0, "day_start", 1)
            # Expand to day rows (one row per day) for compatibility
            out = pd.DataFrame({
                "day": np.arange(1, len(pred_row) + 1),
                **{cols[i]: [float(pred_row[i])] for i in range(len(pred_row))}
            })
            return out
        # if model returned (1, n_targets) where n_targets != horizon, fall through to iterative below
    except Exception:
        # one-shot attempt failed (model not shaped for this) -> fall back to iterative
        pass

    if not iterative_if_needed:
        raise RuntimeError("Model did not produce full-horizon prediction and iterative mode disabled.")

    # 2) Iterative (recursive) prediction — safe update of window so values change
    # We'll keep a mutable buffer of recent rows in unscaled (original) units for easier updates
    # Start buffer as the historical values (unscaled)
    buffer_unscaled = X_hist.copy()  # shape (n_hist, n_features)

    preds_list = []  # will hold per-day predicted arrays

    for step in range(horizon):
        # Prepare input: scale the last available row (or some aggregate)
        input_unscaled = buffer_unscaled[-1:].astype(np.float64)  # shape (1, n_features)
        input_scaled = scaler.transform(input_unscaled)

        # Model may expect 2D (n_samples, n_features) or 3D (n_samples, timesteps, features).
        # We try predict directly; if model expects sequences, adapt by reshaping.
        try:
            next_pred = model.predict(input_scaled)
        except Exception:
            # Try adding a time dimension (1,1,n_features) — some sequence models accept that
            try:
                next_pred = model.predict(input_scaled.reshape(1, 1, -1))
            except Exception as e:
                raise RuntimeError(f"Model.predict failed on scaled input: {e}")

        next_pred = np.asarray(next_pred)
        # normalized to 1D vector per sample: prefer flattened first sample
        if next_pred.ndim == 2 and next_pred.shape[0] == 1:
            next_vals = next_pred[0].astype(np.float64)
        elif next_pred.ndim == 1:
            next_vals = next_pred.astype(np.float64)
        else:
            # If model returned multi-dim (e.g., (1,1,n_out)), collapse last axis
            next_vals = next_pred.reshape(-1).astype(np.float64)

        next_vals = _safe_numeric(next_vals)
        preds_list.append(next_vals.copy())

        # --- update buffer_unscaled so next iteration sees changed inputs ---
        # Best-effort mapping: if feature names include Ap/F107/Kp, try mapping predictions into them.
        # If next_vals has length==1 -> map to 'Kp' if present else first feature.
        # If length>=2 -> map first two values to 'Ap' and 'F107' if present, else fill first columns.

        # get feature names if available
        # Note: caller passed feature_cols; reconstruct order via history_df
        # we have access to column names through history_df; assume same order as feature_cols
        # (feature_cols is required and validated earlier)
        # To avoid circular import, we don't require explicit feature_cols param here (but we will)
        # So re-check: ensure history_df was created from same feature_cols order.
        # We'll rely on column positions.

        # Try to set Ap and F107 if exist:
        col_names = list(history_df.columns) if 'history_df' in globals() else None
        # Instead, use passed feature_cols by reading from input param (we have it available)
        # We know feature_cols from caller scope - use that.
        # To access it here, we need to accept it as param; ensure generate... signature contains it (it does).

        # Map next_vals into unscaled row
        updated_row = input_unscaled[0].copy()  # unscaled numbers

        # Helper to set by name using passed feature_cols (guaranteed present)
        def _set_by_name(name: str, value: float):
            if name in feature_cols:
                idx = feature_cols.index(name)
                updated_row[idx] = float(value)
                return True
            return False

        # mapping strategy
        if next_vals.size == 1:
            # single-value -> try Kp else first feature
            if not _set_by_name("Kp", next_vals[0]):
                updated_row[0] = float(next_vals[0])
        else:
            # multi-value -> try Ap and F107
            if _set_by_name("Ap", next_vals[0]) or _set_by_name("ap", next_vals[0]):
                # try second
                if not _set_by_name("F107", next_vals[1]) and not _set_by_name("F10.7", next_vals[1]):
                    # fallback: put second to next numeric slot
                    for idx in range(len(updated_row)):
                        if idx != (feature_cols.index("Ap") if "Ap" in feature_cols else -1):
                            updated_row[idx] = float(next_vals[1])
                            break
            else:
                # can't map to named Ap -> write sequentially into first columns
                for i in range(min(next_vals.size, updated_row.size)):
                    updated_row[i] = float(next_vals[i])

        # Append updated row to buffer_unscaled (so future prediction sees changed features)
        buffer_unscaled = np.vstack([buffer_unscaled, updated_row.reshape(1, -1)])

    # After loop, assemble predictions matrix
    preds_arr = np.vstack(preds_list)  # shape (horizon, n_pred_per_step)
    # Name columns generically
    n_preds = preds_arr.shape[1]
    if n_preds == 1:
        cols = ["pred_value"]
    else:
        cols = [f"pred_{i}" for i in range(n_preds)]

    out_df = pd.DataFrame(preds_arr, columns=cols)
    out_df.insert(0, "day", np.arange(1, preds_arr.shape[0] + 1))
    # Ensure numeric Python floats
    for c in cols:
        out_df[c] = out_df[c].apply(lambda v: float(np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)))
    return out_df
