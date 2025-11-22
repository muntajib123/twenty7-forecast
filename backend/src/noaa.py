# backend/src/noaa.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

import requests

NOAA_27DO_URL = "https://services.swpc.noaa.gov/text/27-day-outlook.txt"

# cache location: backend/data/noaa_27day_latest.json
CACHE_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "noaa_27day_latest.json"

ISSUED_RE_COLON = re.compile(
    r":Issued:\s*(?P<yyyy>\d{4})\s+(?P<mon>[A-Za-z]{3})\s+(?P<dd>\d{2})\s+(?P<hh>\d{2})(?P<mm>\d{2})\s*UTC"
)
ISSUED_RE_PLAIN = re.compile(
    r"Issued\s+(?P<yyyy>\d{4})[-/](?P<mm>\d{2})[-/](?P<dd>\d{2})"
)
LINE_RE = re.compile(
    r"^\s*(?P<yyyy>\d{4})\s+(?P<mon>[A-Za-z]{3})\s+(?P<dd>\d{2})\s+"
    r"(?P<f107>\d+)\s+(?P<ap>\d+)\s+(?P<kp>\d+)\s*$"
)
MON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1
)}

def _parse_issued_utc(text: str) -> str | None:
    m = ISSUED_RE_COLON.search(text)
    if m:
        yyyy = int(m["yyyy"])
        mon = MON.get(m["mon"], 1)
        dd = int(m["dd"])
        hh = int(m["hh"]); mm = int(m["mm"])
        ts = datetime(yyyy, mon, dd, hh, mm, tzinfo=timezone.utc)
        return ts.isoformat().replace("+00:00", "Z")
    m2 = ISSUED_RE_PLAIN.search(text)
    if m2:
        yyyy = int(m2["yyyy"]); mm = int(m2["mm"]); dd = int(m2["dd"])
        ts = datetime(yyyy, mm, dd, tzinfo=timezone.utc)
        return ts.isoformat().replace("+00:00", "Z")
    return None

def _parse_27do_lines(text: str) -> List[Dict]:
    days: List[Dict] = []
    for raw in text.splitlines():
        m = LINE_RE.match(raw)
        if not m:
            continue
        yyyy = int(m["yyyy"]); mon = MON.get(m["mon"], 1); dd = int(m["dd"])
        dt = datetime(yyyy, mon, dd, tzinfo=timezone.utc)
        f107 = int(m["f107"]); ap = int(m["ap"]); kp = int(m["kp"])
        days.append({
            "date_utc": dt.isoformat().replace("+00:00", "Z"),
            "f107": f107,        # Radio Flux 10.7 cm
            "ap": ap,            # Planetary A index
            "kp_noaa": kp,       # Largest Kp (NOAA)
        })
    return days

def fetch_27do_text(timeout: float = 20.0) -> str:
    r = requests.get(NOAA_27DO_URL, timeout=timeout)
    r.raise_for_status()
    return r.text

def get_live_payload() -> Dict:
    text = fetch_27do_text()
    issued = _parse_issued_utc(text)
    days = _parse_27do_lines(text)
    if not days:
        raise ValueError("No rows parsed from NOAA 27-day outlook.")
    return {
        "source": "NOAA SWPC 27-Day Outlook",
        "issued_utc": issued,
        "days": days,
    }

def save_cache(payload: Dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_cache() -> Dict | None:
    if not CACHE_FILE.exists():
        return None
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
