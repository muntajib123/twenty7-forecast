"""
Feature extender for predict/beyond.

Deterministic extension methods for f107 and ap series.
Supported modes:
  - "mean7"  : future day = mean(previous 7 days)         (flat-ish)
  - "linear" : linear extrapolation using slope of last 7 days
  - "ar1"    : simple AR(1) estimate from last-up-to-7 pairs
  - "trend"  : deterministic trend continuation using slope (no randomness)

This file also applies the requested domain fixes:
 - Any F10.7 value that is missing, zero, or < 115 will be replaced with
   a plausible value in [120, 138] with deterministic variation per-day
   (so numbers are not all identical but reproducible).
"""
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _safe_float(v, fallback=None):
    try:
        if v is None:
            return np.nan
        if pd.isna(v):
            return np.nan
        return float(v)
    except Exception:
        return np.nan


def _extend_series_deterministic(base_vals: List[float], n_extra: int = 27, mode: str = "trend"):
    base = [float(x) for x in base_vals]
    if len(base) == 0:
        return [0.0] * n_extra

    n = len(base)
    total_len = n + n_extra
    series = base.copy()

    for i in range(n, total_len):
        k = min(7, len(series))
        prev_window = series[-k:] if k > 0 else series

        if mode == "mean7":
            next_val = float(np.mean(prev_window)) if len(prev_window) > 0 else series[-1]
        elif mode == "linear":
            if len(prev_window) >= 2:
                x = np.arange(len(prev_window))
                y = np.array(prev_window)
                a, b = np.polyfit(x, y, 1)  # slope, intercept
                next_val = float(a * (len(prev_window)) + b)
            else:
                next_val = series[-1]
        elif mode == "ar1":
            w = prev_window
            if len(w) < 2:
                next_val = series[-1]
            else:
                x = np.array(w[:-1])
                y = np.array(w[1:])
                denom = (x * x).sum()
                if denom == 0:
                    phi = 0.0
                else:
                    phi = float((x * y).sum() / denom)
                next_val = float(phi * w[-1])
        elif mode == "trend":
            k2 = min(7, len(prev_window))
            if k2 >= 2:
                x = np.arange(k2)
                y = np.array(prev_window[-k2:])
                a, b = np.polyfit(x, y, 1)
                next_val = float(a * k2 + b)
            else:
                next_val = series[-1]
        else:
            next_val = float(np.mean(prev_window)) if len(prev_window) > 0 else series[-1]

        if not np.isfinite(next_val):
            next_val = series[-1]
        next_val = max(0.0, next_val)
        series.append(next_val)

    return series


def _extend_series_with_optional_noise(base_vals: List[float], n_extra: int = 27, mode: str = "trend",
                                       add_noise: bool = False, seed: Optional[int] = None):
    ext = _extend_series_deterministic(base_vals, n_extra=n_extra, mode=mode)
    if add_noise:
        rng = np.random.RandomState(seed) if seed is not None else np.random.RandomState(0)
        base_len = len(base_vals)
        for i in range(base_len, len(ext)):
            val = ext[i]
            noise_scale = max(0.5, abs(val) * 0.03)
            ext[i] = float(max(0.0, val + rng.normal(0.0, noise_scale)))
    return ext


def label_dates(start_dt_utc: datetime, n_days: int):
    return [(start_dt_utc + timedelta(days=i)).date().isoformat() for i in range(n_days)]


def _f107_fix_value(idx: int, seed: Optional[int] = None) -> float:
    """
    Deterministic plausible F10.7 value in [120, 138] for day index `idx`.
    This avoids giving identical numbers for every replaced day while staying reproducible.
    """
    s = seed if seed is not None else 7
    base = 120
    # mix with simple modular arithmetic to produce variation 0..18
    variation = (idx * 13 + s * 3) % 19
    return float(base + variation)


def build_extended_feature_row(base_row: Dict[str, float], mode: str = "trend",
                               add_noise: bool = False, seed: Optional[int] = None) -> pd.DataFrame:
    """
    Build extended features DataFrame with columns f107_d1..f107_d54 and ap_d1..ap_d54.
    - base_row: dict with f107_d1..f107_d27 and ap_d1..ap_d27 (can contain NaN/None)
    - mode: "mean7", "linear", "ar1", or "trend"
    - add_noise: optionally add small reproducible noise (requires seed)
    - seed: integer for reproducible noise (optional)
    """

    # Read base values but produce NaN if missing or invalid
    f107 = [_safe_float(base_row.get(f"f107_d{i}", None)) for i in range(1, 28)]
    ap =   [_safe_float(base_row.get(f"ap_d{i}",   None)) for i in range(1, 28)]

    # Convert to pandas Series to do robust imputation across the 27-window
    f107_s = pd.Series(f107, dtype="float64")
    ap_s = pd.Series(ap, dtype="float64")

    # Row-wise imputation: forward-fill then back-fill using available neighbors
    # use pandas ffill/bfill across columns in the row context
    f107_s = f107_s.ffill().bfill()
    ap_s = ap_s.ffill().bfill()

    # If entire series is NaN, apply domain fallback (choose a mid-high quiet baseline)
    if f107_s.isna().all():
        f107_s = f107_s.fillna(129.0)
    if ap_s.isna().all():
        ap_s = ap_s.fillna(5.0)

    # After ffill/bfill some entries may remain NaN (e.g. mid-window), fill them with local mean or domain fallback
    if f107_s.isna().any():
        local_mean = f107_s.mean(skipna=True)
        if pd.isna(local_mean):
            local_mean = 129.0
        f107_s = f107_s.fillna(local_mean)

    if ap_s.isna().any():
        local_mean_ap = ap_s.mean(skipna=True)
        if pd.isna(local_mean_ap):
            local_mean_ap = 5.0
        ap_s = ap_s.fillna(local_mean_ap)

    # ------------------------------
    # USER REQUEST: replace F10.7 entries that are 0 or <115 with plausible 120..138 values
    # ------------------------------
    for idx in range(len(f107_s)):
        val = f107_s.iloc[idx]
        if (pd.isna(val)) or (not np.isfinite(val)) or (float(val) <= 115.0):
            f107_s.iloc[idx] = _f107_fix_value(idx + 1, seed=seed)

    # Convert series to plain python floats now
    f107_clean = [float(x) for x in f107_s.tolist()]
    ap_clean = [float(x) for x in ap_s.tolist()]

    # Now we have a clean 27-length vector for each; extend them deterministically
    f107_ext = _extend_series_with_optional_noise(list(f107_clean), n_extra=27, mode=mode, add_noise=add_noise, seed=seed)
    ap_ext   = _extend_series_with_optional_noise(list(ap_clean),   n_extra=27, mode=mode, add_noise=add_noise, seed=(seed+1 if seed is not None else None))

    # clip, round (keep reasonable precision)
    f107_ext = [round(max(0.0, float(x)), 3) for x in f107_ext]
    ap_ext   = [round(max(0.0, float(x)), 3) for x in ap_ext]

    out = {}
    for i, val in enumerate(f107_ext, start=1):
        out[f"f107_d{i}"] = val
    for i, val in enumerate(ap_ext, start=1):
        out[f"ap_d{i}"] = val

    df = pd.DataFrame([out])
    return df
