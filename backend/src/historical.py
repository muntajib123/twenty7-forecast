# backend/src/historical.py
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Optional
import os
import glob
import csv
import io
from datetime import datetime

router = APIRouter(prefix="/api/historical", tags=["historical"])

# Folder where you put raw NOAA 27DO text files
RAW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "raw"))
CSV_CACHE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "historical.csv"))

MONTHS = {
    'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
    'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12
}

def parse_line_tokens(tokens: List[str]):
    """
    Expect tokens like: ['2019', 'Jan', '07', '72', '8', '3']
    Returns dict or None.
    """
    if len(tokens) < 6:
        return None
    try:
        year = int(tokens[0])
        mon = tokens[1]
        day = int(tokens[2])
        f107 = float(tokens[3])
        ap = float(tokens[4])
        kp = float(tokens[5])
        mon_n = MONTHS.get(mon[:3])
        if not mon_n:
            return None
        dt = datetime(year, mon_n, day)
        return {"date": dt.strftime("%Y-%m-%d"), "f107": f107, "ap": ap, "kp": kp}
    except Exception:
        return None

def parse_file(path: str):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            # Skip header/comment lines (non-leading-digit)
            if not line[0].isdigit():
                continue
            # Tokenize by whitespace, handle a few variants
            tokens = line.split()
            parsed = parse_line_tokens(tokens)
            if parsed:
                rows.append(parsed)
    return rows

def parse_all_raw():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "27DO*.txt")) + glob.glob(os.path.join(RAW_DIR, "*.txt")))
    all_rows = []
    for f in files:
        all_rows.extend(parse_file(f))
    # deduplicate by date (keep last seen)
    seen = {}
    for r in all_rows:
        seen[r["date"]] = r
    result = sorted(seen.values(), key=lambda x: x["date"])
    return result

def ensure_csv_cache():
    # if cache missing, build from raw
    if not os.path.exists(CSV_CACHE):
        rows = parse_all_raw()
        os.makedirs(os.path.dirname(CSV_CACHE), exist_ok=True)
        with open(CSV_CACHE, "w", newline="", encoding="utf-8") as cf:
            w = csv.DictWriter(cf, fieldnames=["date","f107","ap","kp"])
            w.writeheader()
            for r in rows:
                w.writerow(r)

@router.get("", response_class=JSONResponse)
def get_historical(start: Optional[str] = Query(None), end: Optional[str] = Query(None), format: Optional[str] = Query("json")):
    """
    GET /api/historical?start=YYYY-MM-DD&end=YYYY-MM-DD&format=json|csv
    - If CSV requested, returns downloadable CSV.
    - If JSON, returns an array of rows [{date,f107,ap,kp}, ...].
    """
    try:
        # prefer CSV cache if present for speed, otherwise parse raw files
        if os.path.exists(CSV_CACHE):
            rows = []
            with open(CSV_CACHE, "r", encoding="utf-8") as cf:
                r = csv.DictReader(cf)
                for rr in r:
                    rows.append({"date": rr["date"], "f107": float(rr["f107"]) if rr["f107"]!="" else None,
                                 "ap": float(rr["ap"]) if rr["ap"]!="" else None,
                                 "kp": float(rr["kp"]) if rr["kp"]!="" else None})
        else:
            rows = parse_all_raw()

        # date filters
        if start:
            # validate format
            _ = datetime.strptime(start, "%Y-%m-%d")
            rows = [r for r in rows if r["date"] >= start]
        if end:
            _ = datetime.strptime(end, "%Y-%m-%d")
            rows = [r for r in rows if r["date"] <= end]

        if format == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=["date","f107","ap","kp"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
            buf.seek(0)
            return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                     headers={"Content-Disposition":"attachment; filename=historical.csv"})
        return JSONResponse(rows)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
