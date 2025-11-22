// src/utils/normalize.js
import dayjs from "dayjs";
import { extractForecast } from "./extractForecast";

/** ---------- helpers ---------- */
const MS_PER_DAY = 86400000;

const toISO = (dateLike) => {
  if (!dateLike) return null;
  const d = new Date(dateLike);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
};

const toNum = (v) => {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const n = +String(v).replace(/,/g, "");
  return Number.isFinite(n) ? n : null;
};

const round1 = (n) => (n == null ? null : Math.round(n * 10) / 10);

const clamp = (n, lo, hi) =>
  n == null ? null : Math.min(hi, Math.max(lo, n));

const kpToAp = (kpInt) => {
  const t = { 0: 0, 1: 3, 2: 7, 3: 15, 4: 27, 5: 48, 6: 80, 7: 140, 8: 240, 9: 400 };
  return t[kpInt] ?? null;
};

const ensureLabel = (iso, idx) =>
  iso ? dayjs(iso).format("MMM D") : `D${idx + 1}`;

const byDateThenIdx = (a, b) => {
  if (a.date && b.date) return a.date.localeCompare(b.date);
  if (a.date) return -1;
  if (b.date) return 1;
  return a.__i - b.__i;
};

/** ---------- memo cache (per input array reference) ---------- */
const MEMO = new WeakMap();

/**
 * normalize(input)
 * - If input is an array, treats it as day rows.
 * - If input is an object/payload, calls extractForecast first.
 * Output rows have stable shape: { id, date(ISO|null), kp, ap, f107, note, label }
 */
export function normalize(input) {
  const rowsIn = Array.isArray(input) ? input : extractForecast(input);

  // memoize by reference + simple stamp
  const cached = MEMO.get(rowsIn);
  if (cached?.stamp === stamp(rowsIn)) return cached.value;

  // 1) map + clean
  const mapped = rowsIn.map((d, i) => {
    const iso = d?.date ? toISO(d.date) : null;

    const kpRaw = toNum(d?.kp ?? d?.Kp ?? d?.kp_index ?? d?.KpIndex);
    const kp = clamp(round1(kpRaw), 0, 9);

    let ap = toNum(d?.ap ?? d?.Ap ?? d?.ap_index);
    if (ap == null && kp != null) ap = kpToAp(Math.round(kp));

    const f107 = toNum(d?.f107 ?? d?.F107 ?? d?.f10_7 ?? d?.solar_flux);

    return {
      __i: i, // for stable secondary sort
      id: d?.id ?? iso ?? i,
      date: iso,
      kp,
      ap,
      f107,
      note: d?.note ?? d?.comment ?? null,
      label: d?.label ?? ensureLabel(iso, i),
    };
  });

  // 2) sort by date, then original index
  mapped.sort(byDateThenIdx);

  // 3) de-dupe by date (keep first occurrence)
  const seenDates = new Set();
  const deduped = [];
  for (let i = 0; i < mapped.length; i++) {
    const r = mapped[i];
    const key = r.date || `idx:${r.__i}`;
    if (seenDates.has(key)) continue;
    seenDates.add(key);
    deduped.push(r);
  }

  // 4) strip temp fields
  for (let i = 0; i < deduped.length; i++) delete deduped[i].__i;

  // store memo
  const out = deduped;
  MEMO.set(rowsIn, { stamp: stamp(rowsIn), value: out });
  return out;
}

/** A tiny, cheap stamp so we can reuse memoized results. */
function stamp(arr) {
  // Using length + first/last id is a good compromise between speed and correctness.
  if (!Array.isArray(arr) || arr.length === 0) return "0";
  const first = arr[0]?.id ?? arr[0]?.date ?? "f";
  const last = arr[arr.length - 1]?.id ?? arr[arr.length - 1]?.date ?? "l";
  return `${arr.length}|${first}|${last}`;
}

/** ---------- selectors for UI ---------- */

/** For charts: [{ label, kp, ap, f107 }] */
export function selectChartItems(rows) {
  const data = normalize(rows);
  return data.map((d) => ({
    label: d.label,
    kp: d.kp,
    ap: d.ap,
    f107: d.f107,
  }));
}

/** For table: rows already good; this adds friendly date+note fallback if you need it */
export function selectTableRows(rows) {
  const data = normalize(rows);
  return data.map((d, i) => ({
    id: d.id,
    date: d.date ? d.date.slice(0, 10) : `Day ${i + 1}`,
    kp: d.kp,
    ap: d.ap,
    f107: d.f107,
    note: d.note ?? "",
    label: d.label,
  }));
}

/** Optional: fill missing contiguous dates (if you ever need a dense timeline) */
export function fillMissingDates(rows) {
  const data = normalize(rows).filter((r) => r.date);
  if (!data.length) return data;

  const start = new Date(data[0].date);
  const end = new Date(data[data.length - 1].date);

  const byIso = new Map(data.map((r) => [r.date.slice(0, 10), r]));
  const out = [];
  for (let t = start.getTime(); t <= end.getTime(); t += MS_PER_DAY) {
    const isoDay = new Date(t).toISOString().slice(0, 10);
    const hit = byIso.get(isoDay);
    out.push(
      hit ?? {
        id: `gap-${isoDay}`,
        date: new Date(t).toISOString(),
        kp: null,
        ap: null,
        f107: null,
        note: null,
        label: dayjs(new Date(t).toISOString()).format("MMM D"),
      }
    );
  }
  return out;
}
