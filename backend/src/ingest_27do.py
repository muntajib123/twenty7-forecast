# backend/src/ingest_27do.py
import argparse
import os
import re
import glob
import pandas as pd
from datetime import datetime

ROW_RE = re.compile(
    r"""^
    (?P<year>\d{4})\s+            # 2025
    (?P<mon>[A-Za-z]{3})\s+       # Oct
    (?P<day>\d{2})\s+             # 06
    (?P<f107>\d+)\s+              # 150  (Radio Flux)
    (?P<ap>\d+)\s+                # 15   (Planetary A Index)
    (?P<kp>\d+)                   # 4    (Largest Kp Index)
    $""",
    re.VERBOSE,
)

def parse_27do_txt(path: str):
    f107, ap, kp = [], [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            m = ROW_RE.match(line)
            if not m:
                continue
            f107.append(float(m.group("f107")))
            ap.append(float(m.group("ap")))
            kp.append(float(m.group("kp")))
    if len(f107) != 27 or len(ap) != 27 or len(kp) != 27:
        raise ValueError(f"{path}: expected 27 rows, got f107={len(f107)}, ap={len(ap)}, kp={len(kp)}")

    def series_to_cols(vals, prefix):
        return {f"{prefix}_d{i+1}": vals[i] for i in range(27)}

    row = {}
    row.update(series_to_cols(f107, "f107"))
    row.update(series_to_cols(ap, "ap"))
    row.update(series_to_cols(kp, "kp"))
    row["source_file"] = os.path.basename(path)
    return row

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw_dir", required=True, help="Folder with 27DO_*.txt files")
    p.add_argument("--out_train", required=True, help="CSV to append/overwrite for training")
    p.add_argument("--out_today", required=True, help="Single-row features CSV for API prediction")
    args = p.parse_args()

    txts = sorted(glob.glob(os.path.join(args.raw_dir, "*.txt")))
    if not txts:
        print(f"No .txt files found in {args.raw_dir}")
        return

    # Build a training dataframe from all files
    rows = []
    for pth in txts:
        try:
            rows.append(parse_27do_txt(pth))
        except Exception as e:
            print(f"Skipping {pth}: {e}")
    if not rows:
        print("Found .txt files but none parsed successfully.")
        return

    df = pd.DataFrame(rows)

    # ---- TRAINING CSV ----
    # We will learn to predict Kp horizon from F10.7 + Ap horizons
    #   Features: f107_d1..d27, ap_d1..d27
    #   Targets:  kp_d1..d27
    feature_cols = [*(f"f107_d{i}" for i in range(1,28)),
                    *(f"ap_d{i}" for i in range(1,28))]
    target_cols  = [f"kp_d{i}" for i in range(1,28)]
    needed = feature_cols + target_cols
    train_df = df[needed + ["source_file"]].copy()
    train_df.to_csv(args.out_train, index=False)
    print(f"Wrote training CSV with {len(train_df)} rows -> {args.out_train}")

    # ---- FEATURES_TODAY CSV ----
    # choose the latest by modified time
    latest_path = max(txts, key=os.path.getmtime)
    latest_row = parse_27do_txt(latest_path)
    features_today = pd.DataFrame([{k: latest_row[k] for k in feature_cols}])
    features_today.to_csv(args.out_today, index=False)
    print(f"Wrote features_today CSV -> {args.out_today} (from {os.path.basename(latest_path)})")

if __name__ == "__main__":
    main()
