import pandas as pd

def dict_to_feature_df(features: dict, feature_cols):
    df = pd.DataFrame([features])
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0
    return df[feature_cols]
