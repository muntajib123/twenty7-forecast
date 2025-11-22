# backend/tools/convert_noaa_to_csv.py
import os, glob, csv, re
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(ROOT, "raw")
OUT_DIR = os.path.join(ROOT, "data")
OUT_FILE = os.path.join(OUT_DIR, "historical.csv")

MONTHS = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}

line_re = re.compile(r'^\s*(\d{4})\s+([A-Za-z]{3})\s+(\d{1,2})\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$')

def parse_file(path):
    rows=[]
    with open(path,'r',encoding='utf-8',errors='ignore') as f:
        for line in f:
            m = line_re.match(line)
            if not m:
                continue
            y=int(m.group(1)); mon=m.group(2); d=int(m.group(3))
            f107=int(m.group(4)); ap=int(m.group(5)); kp=int(m.group(6))
            try:
                dt=datetime(y, MONTHS[mon], d)
                rows.append({"date":dt.strftime("%Y-%m-%d"), "f107":f107, "ap":ap, "kp":kp})
            except Exception:
                continue
    return rows

def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "27DO*.txt")) + glob.glob(os.path.join(RAW_DIR, "*.txt")))
    seen = {}
    for p in files:
        for r in parse_file(p):
            seen[r["date"]]=r
    rows = sorted(seen.values(), key=lambda x: x["date"])
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=["date","f107","ap","kp"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("Wrote", len(rows), "rows to", OUT_FILE)

if __name__=="__main__":
    main()
