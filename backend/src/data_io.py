from pathlib import Path
import pandas as pd
from typing import List, Tuple, Optional

# Feature/target templates (order matters!)
FEATURE_TEMPLATE: List[str] = [
    *(f"f107_d{i}" for i in range(1, 28)),
    *(f"ap_d{i}"   for i in range(1, 28)),
]
TARGET_TEMPLATE: List[str] = [f"kp_d{i}" for i in range(1, 28)]

# Domain-safe defaults
_F107_DOMAIN_FALLBACK = 129.0   # inside your requested 120-138 band (stable deterministic)
_AP_DOMAIN_FALLBACK = 20.0      # default Ap when missing (will be further adjusted later using kp when available)


def _ensure_cols(df: pd.DataFrame, cols: List[str], fill: Optional[float] = 0.0, dtype: str = "float32") -> pd.DataFrame:
    """
    Ensure all `cols` exist in df, but avoid using physical-zeros as a blind fill.
    - If `fill` is not None (e.g. training pipeline explicitly provides fill=0.0),
      missing values will be filled with that value (backwards compatible).
    - If `fill` is None, we will:
        * create missing columns as NaN,
        * coerce to numeric,
        * perform row-wise forward/back fill (axis=1),
        * apply per-column sensible fallbacks (domain-aware) if still missing,
        * then cast dtype.
    """
    df_local = df.copy()

    # add missing columns as NA (do not inject numeric zeros)
    for c in cols:
        if c not in df_local.columns:
            df_local[c] = pd.NA

    # keep requested order and coerce to numeric
    out = df_local[cols].copy()
    out = out.apply(pd.to_numeric, errors="coerce")

    if fill is None:
        # Row-wise forward then backward fill so we use neighboring day values first
        # axis=1 does ffill/bfill across columns in the same row
        out = out.fillna(method="ffill", axis=1).fillna(method="bfill", axis=1)

        # If any column remains entirely missing for this row, apply sensible per-column fallback
        for c in out.columns:
            if out[c].isna().all():
                name = c.lower()
                if "f107" in name or "f10.7" in name or "f10_7" in name:
                    out[c] = out[c].fillna(_F107_DOMAIN_FALLBACK)
                elif name.startswith("ap_") or name.startswith("apd") or "ap" in name:
                    out[c] = out[c].fillna(_AP_DOMAIN_FALLBACK)
                else:
                    out[c] = out[c].fillna(0.0)

        # final safety: any remaining NaNs -> domain-specific fallback (check column name)
        for c in out.columns:
            if out[c].isna().any():
                name = c.lower()
                if "f107" in name or "f10.7" in name or "f10_7" in name:
                    out[c] = out[c].fillna(_F107_DOMAIN_FALLBACK)
                elif name.startswith("ap_") or name.startswith("apd") or "ap" in name:
                    out[c] = out[c].fillna(_AP_DOMAIN_FALLBACK)
                else:
                    out[c] = out[c].fillna(0.0)

    else:
        # Backwards-compatible behaviour: fill missing with provided numeric value
        out = out.fillna(fill)

    # enforce dtype
    out = out.astype(dtype)
    return out


def load_training_csv(path: str) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], List[str]]:
    """
    Reads the training CSV at `path` and returns:
      X_df (features), y_df (targets), feature_cols, target_cols
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Training CSV not found at {p}")

    df = pd.read_csv(p)
    if df.empty:
        raise ValueError(f"Training CSV is empty at {p}")

    # For training we can keep previous behaviour (explicit numeric fill)
    X_df = _ensure_cols(df, FEATURE_TEMPLATE, fill=0.0, dtype="float32")

    # Targets: enforce columns, then forward/back fill across rows to patch gaps
    y_raw = _ensure_cols(df, TARGET_TEMPLATE, fill=pd.NA, dtype="float32")
    # y_raw initially may contain NaN; fill across rows (ffill/bfill) then fill remaining with 0
    y_df = y_raw.ffill(axis=0).bfill(axis=0).fillna(0.0)

    # Kp physical range guard (0..9)
    y_df = y_df.clip(lower=0.0, upper=9.0).astype("float32")

    return X_df, y_df, FEATURE_TEMPLATE, TARGET_TEMPLATE


def load_features_csv(path: str, feature_cols: List[str]) -> pd.DataFrame:
    """
    Load features_today.csv (or similar). Guarantees:
    - required feature columns exist and are ordered
    - numeric float32 dtype
    - at least one row (uses the FIRST row by convention)
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Features CSV not found at {p}")

    df = pd.read_csv(p)
    if df.empty:
        raise ValueError(f"Features CSV is empty at {p}")

    # Use domain-aware imputation (fill=None) to avoid injecting zeros for F10.7
    out = _ensure_cols(df, list(feature_cols), fill=None, dtype="float32")

    # If multiple rows exist, we use the first row as the active feature window
    return out.iloc[:1].copy()
