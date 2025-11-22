# backend/debug_forecast_test.py
import os
import pandas as pd
from src.model import load_artifacts
from src.data_io import load_training_csv, load_features_csv
from src.forecaster import generate_27day_forecast
from pathlib import Path

# Adjust these paths if your project uses different locations
MODEL_FILE = "models/xgb_multiout.joblib"   # or the path you actually use in config
SCALER_FILE = "models/scaler.joblib"
DATA_PATH = "data/training.csv"
FEATURES_TODAY_PATH = "data/features_today.csv"

print("MODEL_FILE exists:", os.path.exists(MODEL_FILE))
print("SCALER_FILE exists:", os.path.exists(SCALER_FILE))
print("DATA_PATH exists:", os.path.exists(DATA_PATH))
print("FEATURES_TODAY exists:", os.path.exists(FEATURES_TODAY_PATH))

# Load training metadata
try:
    X, y, feature_cols, target_cols = load_training_csv(DATA_PATH)
    print("Training X shape:", X.shape)
    print("Training y shape:", y.shape)
    print("feature_cols (sample):", feature_cols[:8])
except Exception as e:
    print("Failed to load training CSV:", e)
    raise

# Load features_today
try:
    ft = load_features_csv(FEATURES_TODAY_PATH, feature_cols)
    print("features_today shape:", ft.shape)
    print("features_today row sample:", ft.iloc[0].to_dict())
except Exception as e:
    print("Failed to load features_today CSV:", e)
    raise

# Introspect artifacts
try:
    loaded = load_artifacts(MODEL_FILE, SCALER_FILE)
    print("load_artifacts returned:", type(loaded))
    if isinstance(loaded, tuple) and len(loaded) == 2:
        a, b = loaded
        print("first type:", type(a), "has_transform:", hasattr(a, "transform"), "has_predict:", hasattr(a, "predict"))
        print("second type:", type(b), "has_transform:", hasattr(b, "transform"), "has_predict:", hasattr(b, "predict"))
except Exception as e:
    print("Failed to load artifacts:", e)
    raise

# Try one-shot & iterative forecasting
try:
    df_fore = generate_27day_forecast(history_df=X, model_path=MODEL_FILE, scaler_path=SCALER_FILE,
                                      feature_cols=feature_cols, horizon=27)
    print("forecast df shape:", df_fore.shape)
    print(df_fore.head(12))
except Exception as e:
    print("Forecaster failed:", e)
    raise
