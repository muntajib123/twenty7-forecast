from src.trainer import train_and_eval
from src.config import DATA_PATH, MODEL_FILE, SCALER_FILE
try:
    out = train_and_eval(DATA_PATH, MODEL_FILE, SCALER_FILE)
    print("OK:", out)
except Exception as e:
    import traceback
    traceback.print_exc()
