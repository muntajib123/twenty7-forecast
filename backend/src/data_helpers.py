# backend/src/data_helpers.py   (or replace in whichever file contains dict_to_feature_df)
import pandas as pd
from typing import List, Dict

def dict_to_feature_df(features: Dict[str, float], feature_cols: List[str]) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame from a dict.
    - Do NOT inject zeros for missing physical features.
    - Missing columns created as pd.NA, leaving canonical imputation to data_io._ensure_cols via load_features_csv.
    """
    df = pd.DataFrame([features])
    for col in feature_cols:
        if col not in df.columns:
            df[col] = pd.NA
    # Reorder to canonical columns and return; numeric coercion & imputation handled by data_io functions
    return df[feature_cols]
