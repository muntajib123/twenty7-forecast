// src/utils/extractForecast.js
import dayjs from "dayjs";

/**
 * Output shape (stable):
 * [{ id, date: ISO|null, kp: number|null, ap: number|null, f107: number|null, note: string|null, label: string }, ...]
 */

const WRAPPER_KEYS = ["forecast", "predictions", "data", "items", "result", "values", "latest"];
const KP_KEYS = ["kp", "Kp", "kp_index", "KpIndex"];
const AP_KEYS = ["ap", "Ap", "ap_index"];
const F107_KEYS = ["f107", "F107", "f10_7", "solar_flux"];
const DATE_ARRAY_KEYS = ["dates", "date"];
const MS_PER_DAY = 86400000;

/* ---------- tiny helpers ---------- */
const toNum = (v) => {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const n = +String(v).replace(/,/g, "");
  return Number.isFinite(n) ? n : null;
};

const toISO = (dateLike) => {
  if (!dateLike) return null;
  const d = new Date(dateLike);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
};

const firstArray = (obj, keys) => {
  for (const k of keys) {
    const v = obj?.[k];
    if (Array.isArray(v)) return v;
  }
  return null;
};

const firstScalar = (obj, keys) => {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && !Array.isArray(v)) return v;
  }
  return null;
};

const looksLikeDay = (o) => {
  if (!o || typeof o !== "object") return false;
  const keys = Object.keys(o);
  return KP_KEYS.some((k) => keys.includes(k));
};

const buildDatesFromStart = (startISO, n) => {
  const out = new Array(n);
  if (!startISO || !n) return [];
  const base = new Date(`${startISO}T00:00:00Z`);
  if (Number.isNaN(base.getTime())) return [];
  for (let i = 0; i < n; i++) {
    const d = new Date(base.getTime() + i * MS_PER_DAY);
    out[i] = d.toISOString().slice(0, 10);
  }
  return out;
};

/* ---------- final shaping ---------- */
const kpToAp = (kpInt) => {
  const t = { 0: 0, 1: 3, 2: 7, 3: 15, 4: 27, 5: 48, 6: 80, 7: 140, 8: 240, 9: 400 };
  return t[kpInt] ?? null;
};

const massage = (arr) => {
  const res = new Array(arr.length);
  for (let idx = 0; idx < arr.length; idx++) {
    const d = arr[idx] ?? {};
    const iso = d.date ? toISO(String(d.date)) : null;

    const kpVal = toNum(d.kp ?? d.Kp ?? d.kp_index ?? d.KpIndex);
    let apVal = toNum(d.ap ?? d.Ap ?? d.ap_index);
    if (apVal == null && Number.isFinite(kpVal)) apVal = kpToAp(Math.round(kpVal));
    const f107Val = toNum(d.f107 ?? d.F107 ?? d.f10_7 ?? d.solar_flux);

    res[idx] = {
      id: d.id ?? iso ?? idx,
      date: iso,
      kp: kpVal,
      ap: apVal,
      f107: f107Val,
      note: d.note ?? d.comment ?? null,
      label: iso ? dayjs(iso).format("MMM D") : `D${idx + 1}`,
    };
  }
  return res;
};

/* ---------- main ---------- */
export function extractForecast(payload) {
  if (!payload) return [];

  // 1) Backend: horizon + (dates_utc | beyond_start_utc | meta.*)
  if (Array.isArray(payload.horizon)) {
    const horizon = payload.horizon;

    const explicitDates =
      Array.isArray(payload.dates_utc) && payload.dates_utc.length === horizon.length
        ? payload.dates_utc
        : null;

    const startISO =
      payload.beyond_start_utc ||
      payload?.meta?.beyond_start_utc ||
      payload?.meta?.start_date_day1_utc ||
      null;

    const dates = explicitDates ?? buildDatesFromStart(startISO, horizon.length);

    // Accept Ap/F10.7 as arrays OR single scalars (top-level/meta)
    const apArr = firstArray(payload, AP_KEYS);
    const fArr = firstArray(payload, F107_KEYS);
    const apScalar = firstScalar(payload, AP_KEYS) ?? firstScalar(payload?.meta, AP_KEYS);
    const fScalar = firstScalar(payload, F107_KEYS) ?? firstScalar(payload?.meta, F107_KEYS);

    const rows = new Array(horizon.length);
    for (let i = 0; i < horizon.length; i++) {
      rows[i] = {
        date: dates?.[i] ?? null,
        kp: toNum(horizon[i]),
        ap: toNum(apArr?.[i] ?? apScalar),
        f107: toNum(fArr?.[i] ?? fScalar),
      };
    }
    return massage(rows);
  }

  // 2) Raw array payload
  if (Array.isArray(payload)) return massage(payload);

  // 3) Known wrapper keys
  for (const k of WRAPPER_KEYS) {
    if (Array.isArray(payload[k])) return massage(payload[k]);
  }

  // 4) Columnar fields: { dates:[], kp:[], ap?:[], f107?:[] }
  const dkey = DATE_ARRAY_KEYS.find((k) => Array.isArray(payload[k]));
  const kpkey = KP_KEYS.find((k) => Array.isArray(payload[k]));
  if (dkey && kpkey) {
    const len = Math.min(payload[dkey].length, payload[kpkey].length);
    const apArr = firstArray(payload, AP_KEYS);
    const fArr = firstArray(payload, F107_KEYS);

    const rows = new Array(len);
    for (let i = 0; i < len; i++) {
      rows[i] = {
        date: payload[dkey][i],
        kp: toNum(payload[kpkey][i]),
        ap: toNum(apArr?.[i]),
        f107: toNum(fArr?.[i]),
      };
    }
    return massage(rows);
  }

  // 5) D1..D27 object pattern
  const dayEntries = Object.entries(payload).filter(
    ([k, v]) => /^D\d+$/.test(k) && v && typeof v === "object"
  );
  if (dayEntries.length) {
    const rows = dayEntries
      .sort(([a], [b]) => parseInt(a.slice(1), 10) - parseInt(b.slice(1), 10))
      .map(([, v]) => ({
        date: v.date ?? null,
        kp: toNum(v.kp ?? v.Kp ?? v.kp_index ?? v.KpIndex),
        ap: toNum(v.ap ?? v.Ap ?? v.ap_index),
        f107: toNum(v.f107 ?? v.F107 ?? v.f10_7 ?? v.solar_flux),
        note: v.note ?? v.comment ?? null,
      }));
    return massage(rows);
  }

  // 6) Single-day object
  if (looksLikeDay(payload)) return massage([payload]);

  return [];
}

/* ---------- KPIs (single pass) ---------- */
export function calcKpis(items) {
  if (!items?.length) return { window: "—", kpMax: "—", kpAvg: "—", apMax: "—" };

  let kpCount = 0, kpSum = 0, kpMax = -Infinity, apMax = -Infinity;
  let start = null, end = null;

  for (let i = 0; i < items.length; i++) {
    const d = items[i];
    if (d?.date && !start) start = d.date;
    if (d?.date) end = d.date;

    const kp = d?.kp;
    if (Number.isFinite(kp)) {
      kpSum += kp;
      kpCount++;
      if (kp > kpMax) kpMax = kp;
    }

    const ap = d?.ap;
    if (Number.isFinite(ap) && ap > apMax) apMax = ap;
  }

  const round = (n) => (n == null || !Number.isFinite(n) ? "—" : Math.round(n * 10) / 10);

  return {
    window: start && end ? `${String(start).slice(0, 10)} → ${String(end).slice(0, 10)}` : `${items.length} days`,
    kpMax: round(kpCount ? kpMax : null),
    kpAvg: round(kpCount ? kpSum / kpCount : null),
    apMax: round(Number.isFinite(apMax) ? apMax : null),
  };
}
