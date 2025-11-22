# backend/src/forecaster.py
"""
Robust 27-day forecaster.

Usage:
    from .forecaster import generate_27day_forecast
    kp_df = generate_27day_forecast(history_df, MODEL_FILE, SCALER_FILE, feature_cols, horizon=27)

Returns:
    pandas.DataFrame with columns ['day', 'kp'] (length == horizon)
"""
import os
import numpy as np
import pandas as pd
from typing import List, Any, Tuple

from .model import load_artifacts

# ---------- Helpers ----------
def _safe_numeric(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64)
    return np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)

def _try_unpack_loaded(load_ret: Any) -> Tuple[Any, Any]:
    """
    Accept either (scaler, model) or (model, scaler).
    Return (model, scaler).
    """
    if isinstance(load_ret, tuple) and len(load_ret) == 2:
        a, b = load_ret
        # prefer to detect scaler by .transform, model by .predict
        if hasattr(a, "transform") and hasattr(b, "predict"):
            return b, a
        if hasattr(b, "transform") and hasattr(a, "predict"):
            return a, b
        # fallback: assume (scaler, model)
        return b, a
    raise RuntimeError("load_artifacts returned unexpected object; expected a 2-tuple")

def _is_finite_number(x):
    try:
        return np.isfinite(float(x))
    except Exception:
        return False

# ---------- Core ----------
def generate_27day_forecast(history_df: pd.DataFrame,
                            model_path: str,
                            scaler_path: str,
                            feature_cols: List[str],
                            horizon: int = 27,
                            verbose: bool = True) -> pd.DataFrame:
    """
    Generate a horizon-day forecast (KP series) using the saved model/scaler.

    Parameters
    - history_df: DataFrame with exactly the feature_cols in same order used for training (at least 1 row)
    - model_path, scaler_path: file paths to saved artifacts (joblib)
    - feature_cols: ordered list of feature column names
    - horizon: number of days to forecast (default 27)

    Returns:
    - DataFrame with columns ['day', 'kp'] and length == horizon
    """
    if verbose:
        print("[forecaster] start generate_27day_forecast")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"Scaler file not found: {scaler_path}")

    loaded = load_artifacts(model_path, scaler_path)
    model, scaler = _try_unpack_loaded(loaded)

    if not hasattr(scaler, "transform"):
        raise RuntimeError("Loaded scaler has no transform() method")

    # prepare numeric history matrix
    X_hist = _safe_numeric(history_df[feature_cols].values)
    if X_hist.shape[0] < 1:
        raise ValueError("history_df must contain at least one row")

    n_timesteps, n_features = X_hist.shape
    if verbose:
        print(f"[forecaster] history shape: {X_hist.shape}; feature_cols len: {len(feature_cols)}")
        try:
            print("[forecaster] scaler.mean_ shape:", getattr(scaler, "mean_", None) and scaler.mean_.shape)
        except Exception:
            pass
        try:
            print("[forecaster] model type:", type(model), "has_predict:", hasattr(model, "predict"))
        except Exception:
            pass

    # We'll use the last available row as the starting input
    last_unscaled = X_hist[-1:].astype(np.float64)  # shape (1, n_features)
    last_scaled = scaler.transform(last_unscaled)

    if verbose:
        print("[forecaster] last_unscaled sample[:8]:", last_unscaled[0, :min(8, n_features)].tolist())
        print("[forecaster] last_scaled sample[:8]:", last_scaled[0, :min(8, n_features)].tolist())

    # --- Try one-shot prediction (model returns full horizon) ---
    try:
        # Try 2D input first (sklearn-friendly), then 3D if 2D fails
        one = None
        try:
            one = model.predict(last_scaled)
        except Exception:
            try:
                one = model.predict(last_scaled.reshape(1, 1, -1))
            except Exception:
                one = None

        if one is not None:
            arr = np.asarray(one)
            flat = arr.reshape(-1)
            if verbose:
                print("[forecaster] one-shot predict shape:", arr.shape)
                try:
                    print("[forecaster] one-shot sample[:30]:", flat[:30].tolist())
                except Exception:
                    pass

            # If the flattened output length is >= horizon, interpret as horizon predictions
            if flat.size >= horizon:
                # If exactly horizon, use directly
                if flat.size == horizon:
                    kp_vals = [float(np.nan_to_num(x)) for x in flat[:horizon]]
                    if verbose:
                        print("[forecaster] Interpreted one-shot output as direct KP horizon.")
                    return pd.DataFrame({"day": np.arange(1, horizon+1), "kp": kp_vals})
                # If length equals horizon * n_features, attempt to reshape and inverse_transform
                if flat.size == horizon * n_features:
                    try:
                        arr2 = arr.reshape(horizon, n_features)
                        if verbose:
                            print("[forecaster] Interpreting one-shot as (horizon, n_features). Attempt inverse_transform.")
                        unscaled = scaler.inverse_transform(arr2)
                        # find best KP column: look for 'kp' or 'kp_d' in feature_cols
                        lower = [c.lower() for c in feature_cols]
                        kp_idx = None
                        if "kp" in lower:
                            kp_idx = lower.index("kp")
                        else:
                            for idx, nm in enumerate(lower):
                                if nm.startswith("kp_d"):
                                    kp_idx = idx
                                    break
                        if kp_idx is None:
                            kp_idx = 0
                        kp_vals = [float(np.nan_to_num(r[kp_idx])) for r in unscaled[:horizon]]
                        return pd.DataFrame({"day": np.arange(1, horizon+1), "kp": kp_vals})
                    except Exception as e:
                        if verbose:
                            print("[forecaster] one-shot reshape/inverse failed:", e)
                        # fallthrough to iterative
    except Exception as e:
        if verbose:
            print("[forecaster] one-shot attempt error:", e)

    # --- Iterative multi-step fallback (robust) ---
    if verbose:
        print("[forecaster] Falling back to iterative forecasting")

    buffer_unscaled = X_hist.copy()  # append predictions here
    preds = []

    # helper: locate likely indices for ap/f107/kp if needed
    lower_cols = [c.lower() for c in feature_cols]
    def find_col_index(prefixes):
        for p in prefixes:
            if p in lower_cols:
                return lower_cols.index(p)
        # kp_d* style
        for idx, nm in enumerate(lower_cols):
            for p in prefixes:
                if nm.startswith(p):
                    return idx
        return None

    kp_idx_guess = find_col_index(["kp"])
    ap_idx_guess = find_col_index(["ap"])
    f107_idx_guess = find_col_index(["f107", "f10.7", "f10_7"])

    for step in range(horizon):
        inp_unscaled = buffer_unscaled[-1:].astype(np.float64)  # (1, n_features)
        inp_scaled = scaler.transform(inp_unscaled)

        if verbose:
            print(f"[forecaster][step {step+1}] inp_unscaled[:6]:", inp_unscaled[0, :min(6, n_features)].tolist())
            print(f"[forecaster][step {step+1}] inp_scaled[:6]:", inp_scaled[0, :min(6, n_features)].tolist())

        # Try 2D predict, then 3D if 2D fails
        raw = None
        try:
            raw = model.predict(inp_scaled)
        except Exception as e1:
            try:
                raw = model.predict(inp_scaled.reshape(1, 1, -1))
            except Exception as e2:
                if verbose:
                    print(f"[forecaster][step {step+1}] model.predict failed (2D & 3D): {e1} / {e2}")
                raise

        raw = np.asarray(raw)
        flat = raw.reshape(-1)
        if verbose:
            print(f"[forecaster][step {step+1}] raw_pred.shape: {raw.shape}; flat[:8]:", flat[:8].tolist())

        # Case A: model returned exactly n_features -> interpret as full feature vector prediction
        if flat.size == n_features:
            # Decide if these are scaled or unscaled by checking magnitude
            mean_abs = float(np.mean(np.abs(flat)))
            if verbose:
                print(f"[forecaster] n_features output; mean_abs={mean_abs:.4f}")

            # If the vector looks scaled/smallish, inverse_transform
            if mean_abs < 100.0:
                try:
                    unscaled_next = scaler.inverse_transform(flat.reshape(1, -1))[0]
                    if verbose:
                        print(f"[forecaster] inverse_transformed sample[:6]:", unscaled_next[:min(6, n_features)].tolist())
                    # attempt to extract KP value
                    if kp_idx_guess is not None:
                        kp_val = float(np.nan_to_num(unscaled_next[kp_idx_guess]))
                    else:
                        kp_val = float(np.nan_to_num(unscaled_next[0]))
                    preds.append(kp_val)
                    buffer_unscaled = np.vstack([buffer_unscaled, unscaled_next.reshape(1, -1)])
                    continue
                except Exception as e:
                    if verbose:
                        print("[forecaster] inverse_transform failed for n_features-sized output:", e)
                    # fallback: treat flat as raw unscaled
                    unscaled_next = flat.copy()
                    kp_val = float(np.nan_to_num(unscaled_next[0]))
                    preds.append(kp_val)
                    buffer_unscaled = np.vstack([buffer_unscaled, unscaled_next.reshape(1, -1)])
                    continue
            else:
                # assume already unscaled
                unscaled_next = flat.copy()
                kp_val = float(np.nan_to_num(unscaled_next[0]))
                preds.append(kp_val)
                buffer_unscaled = np.vstack([buffer_unscaled, unscaled_next.reshape(1, -1)])
                continue

        # Case B: model returned a single value -> treat as KP one-step
        if flat.size == 1:
            kp_val = float(np.nan_to_num(flat[0]))
            preds.append(kp_val)
            # update buffer: try to write into guessed kp index or into first column
            updated_row = inp_unscaled[0].copy()
            write_idx = kp_idx_guess if kp_idx_guess is not None else 0
            try:
                updated_row[write_idx] = kp_val
                buffer_unscaled = np.vstack([buffer_unscaled, updated_row.reshape(1, -1)])
            except Exception:
                buffer_unscaled = np.vstack([buffer_unscaled, inp_unscaled[0].reshape(1, -1)])
            continue

        # Case C: model returned 3 values (common pattern: kp, ap, f107)
        if flat.size == 3:
            try:
                kp_val = float(np.nan_to_num(flat[0]))
                ap_val = float(np.nan_to_num(flat[1]))
                f107_val = float(np.nan_to_num(flat[2]))
                kp_series_val = kp_val
                preds.append(kp_series_val)
                updated_row = inp_unscaled[0].copy()
                if ap_idx_guess is not None:
                    updated_row[ap_idx_guess] = ap_val
                if f107_idx_guess is not None:
                    updated_row[f107_idx_guess] = f107_val
                if kp_idx_guess is not None:
                    updated_row[kp_idx_guess] = kp_val
                buffer_unscaled = np.vstack([buffer_unscaled, updated_row.reshape(1, -1)])
                continue
            except Exception:
                kp_val = float(np.nan_to_num(flat[0]))
                preds.append(kp_val)
                updated_row = inp_unscaled[0].copy()
                try:
                    updated_row[kp_idx_guess if kp_idx_guess is not None else 0] = kp_val
                    buffer_unscaled = np.vstack([buffer_unscaled, updated_row.reshape(1, -1)])
                except Exception:
                    buffer_unscaled = np.vstack([buffer_unscaled, inp_unscaled[0].reshape(1, -1)])
                continue

        # Case D: model returned a vector of other length (e.g., kp horizon or partial)
        if flat.size == horizon and step == 0:
            kp_vals = [float(np.nan_to_num(x)) for x in flat[:horizon]]
            return pd.DataFrame({"day": np.arange(1, horizon + 1), "kp": kp_vals})

        # Otherwise fallback: take first element as KP
        if flat.size >= 1:
            first = float(np.nan_to_num(flat[0]))
            preds.append(first)
            updated = inp_unscaled[0].copy()
            try:
                if kp_idx_guess is not None:
                    updated[kp_idx_guess] = first
                else:
                    updated[0] = first
                buffer_unscaled = np.vstack([buffer_unscaled, updated.reshape(1, -1)])
            except Exception:
                buffer_unscaled = np.vstack([buffer_unscaled, inp_unscaled[0].reshape(1, -1)])
            continue

        # If nothing matched, append None and carry forward unmodified
        preds.append(None)
        buffer_unscaled = np.vstack([buffer_unscaled, inp_unscaled[0].reshape(1, -1)])

    # Post-process preds -> build kp series of length horizon
    kp_out = []
    for p in preds[:horizon]:
        try:
            if p is None or (not _is_finite_number(p)):
                kp_out.append(None)
            else:
                kp_out.append(round(float(max(0.0, min(9.0, p))), 3))
        except Exception:
            kp_out.append(None)

    if len(kp_out) < horizon:
        kp_out += [None] * (horizon - len(kp_out))

    out_df = pd.DataFrame({"day": np.arange(1, horizon + 1), "kp": kp_out})
    if verbose:
        print("[forecaster] final kp sample (first 10):", out_df["kp"].head(10).tolist())
        print("[forecaster] generate_27day_forecast complete")
    return out_df
