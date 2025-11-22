"""
Builds features_today.csv from the latest NOAA 27-day outlook.
Also (optionally) appends a training row into training.csv using NOAA kp_noaa.

- Features (54 cols):  f107_d1..d27, ap_d1..d27
- Targets (27 cols):   kp_d1..d27  (from NOAA 'kp_noaa')
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

from .config import DATA_PATH, FEATURES_TODAY_PATH
from .data_io import FEATURE_TEMPLATE, TARGET_TEMPLATE
from .noaa import get_live_payload  # live fetcher (does not require Mongo/Store)

# Optional in-memory/Mongo store; safe if unavailable
try:
    from .service import Store
    _HAS_STORE = True
except Exception:
    _HAS_STORE = False


def _noaa_source() -> Dict:
    """
    Prefer the latest saved NOAA doc (if Store is enabled),
    otherwise fetch live directly from NOAA.
    """
    if _HAS_STORE:
        try:
            store = Store()
            doc = store.get_latest_noaa_27day()
            if doc and isinstance(doc.get("days"), list) and len(doc["days"]) >= 27:
                return doc
        except Exception:
            pass

    # Fallback: live fetch
    return get_live_payload()


def _maybe_float_or_nan(v):
    try:
        if v is None:
            return np.nan
        if pd.isna(v):
            return np.nan
        return float(v)
    except Exception:
        return np.nan


def _extract_series(noaa_doc: Dict) -> Tuple[List[float], List[float], List[float], str]:
    """
    From the NOAA payload, extract 27 values for f107, ap, kp_noaa and issued_utc.
    Returns np.nan for missing values (so downstream imputation can run).
    """
    days = noaa_doc.get("days") or []
    if len(days) < 27:
        raise ValueError(f"NOAA doc has only {len(days)} days; need at least 27.")

    f107 = []
    ap = []
    kp = []
    for i in range(27):
        row = days[i]
        f107.append(_maybe_float_or_nan(row.get("f107")))
        ap.append(_maybe_float_or_nan(row.get("ap")))
        kpv = row.get("kp_noaa", None)
        kpf = _maybe_float_or_nan(kpv)
        if not np.isnan(kpf):
            kpf = max(0.0, min(9.0, kpf))
        kp.append(kpf)

    issued_utc = noaa_doc.get("issued_utc") or ""
    return f107, ap, kp, issued_utc


def _build_feature_row(f107: List[float], ap: List[float]) -> Dict[str, float]:
    """
    Map lists to the exact feature column names.
    (We preserve NaN here — domain-specific imputation happens downstream.)
    """
    row: Dict[str, float] = {}
    for i in range(27):
        row[f"f107_d{i+1}"] = f107[i] if not pd.isna(f107[i]) else np.nan
    for i in range(27):
        row[f"ap_d{i+1}"] = ap[i] if not pd.isna(ap[i]) else np.nan
    return row


def _build_training_row(f107: List[float], ap: List[float], kp: List[float], issued_utc: str) -> Dict[str, float]:
    """
    Create a training row containing features + targets + issued_utc.
    If ap is missing but kp exists, compute ap heuristically here before appending.
    (This helps ensure the training CSV contains coherent ap when NOAA omitted it.)
    """
    # Ensure we can derive ap from kp when missing:
    ap_derived = []
    for i in range(27):
        if (not pd.isna(ap[i])):
            ap_derived.append(float(ap[i]))
        else:
            # If kp available, derive ap using heuristic factor 20.0 (close to values you've used)
            if (not pd.isna(kp[i])):
                try:
                    val = float(kp[i]) * 20.0
                    ap_derived.append(round(float(val), 3))
                except Exception:
                    ap_derived.append(np.nan)
            else:
                ap_derived.append(np.nan)

    feature_row = _build_feature_row(f107, ap_derived)
    row = feature_row.copy()
    for i in range(27):
        row[f"kp_d{i+1}"] = kp[i] if not pd.isna(kp[i]) else np.nan
    row["issued_utc"] = issued_utc
    return row


def save_features_today_csv(feature_row: Dict[str, float], path: Path = FEATURES_TODAY_PATH) -> None:
    """
    Write a one-row CSV with only the 54 feature columns in canonical order.
    We keep NaNs in the CSV so the domain-aware imputation in data_io/feature_extend
    can fill using the new domain-aware defaults (F10.7 -> 129.0, AP fallback from kp).
    """
    df = pd.DataFrame([feature_row])
    # Ensure columns exist & ordered
    for c in FEATURE_TEMPLATE:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[FEATURE_TEMPLATE]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"[features_today] wrote features → {path} ({df.shape[1]} cols)")


def append_training_csv(training_row: Dict[str, float], path: Path = DATA_PATH) -> None:
    """
    Append (or create) training.csv with features + targets.
    Deduplicate by 'issued_utc' if present.
    """
    expected_cols = FEATURE_TEMPLATE + TARGET_TEMPLATE + ["issued_utc"]

    if path.exists():
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame(columns=expected_cols)
    else:
        df = pd.DataFrame(columns=expected_cols)

    # Ensure all expected columns exist
    for c in expected_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # Append new row
    new_df = pd.DataFrame([training_row])
    for c in expected_cols:
        if c not in new_df.columns:
            new_df[c] = pd.NA
    new_df = new_df[expected_cols]

    df = pd.concat([df, new_df], ignore_index=True)

    # Drop duplicate issues (keep last)
    if "issued_utc" in df.columns:
        df = df.drop_duplicates(subset=["issued_utc"], keep="last")

    # Do not forcibly fill with zeros here — keep NaNs for downstream domain-imputation
    df = df[expected_cols]

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"[features_today] appended training row → {path} (n_rows={len(df)})")


def rebuild_features_today(write_training: bool = True) -> Dict[str, str]:
    """
    Public entrypoint:
      - loads the latest NOAA doc (store or live),
      - writes features_today.csv,
      - optionally appends a row into training.csv.

    Returns a short summary dict.
    """
    noaa = _noaa_source()
    f107, ap, kp, issued_utc = _extract_series(noaa)

    # If ap missing but kp exists, compute ap now for the feature CSV (so frontends that read features_today see ap)
    for i in range(27):
        if pd.isna(ap[i]) and (not pd.isna(kp[i])):
            try:
                ap[i] = round(float(kp[i]) * 20.0, 3)  # heuristic mapping (kp->ap) chosen to match observed scale
            except Exception:
                ap[i] = np.nan

    feature_row = _build_feature_row(f107, ap)
    save_features_today_csv(feature_row, FEATURES_TODAY_PATH)

    if write_training:
        training_row = _build_training_row(f107, ap, kp, issued_utc)
        append_training_csv(training_row, DATA_PATH)

    return {
        "status": "ok",
        "features_path": str(FEATURES_TODAY_PATH),
        "training_path": str(DATA_PATH),
        "issued_utc": issued_utc,
    }
