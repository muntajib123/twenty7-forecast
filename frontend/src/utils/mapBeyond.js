// utils/mapBeyond.js
export function mapBeyond(payload) {
  const dates = Array.isArray(payload?.dates_utc) ? payload.dates_utc : [];
  const kp = Array.isArray(payload?.horizon) ? payload.horizon : [];
  const ap = Array.isArray(payload?.ap) ? payload.ap : [];
  const f107 = Array.isArray(payload?.f10_7) ? payload.f10_7 : [];

  const n = Math.min(dates.length, kp.length);
  const items = [];
  for (let i = 0; i < n; i++) {
    items.push({
      id: i,
      date: `${dates[i]}T00:00:00Z`,
      kp: Number.isFinite(+kp[i]) ? +kp[i] : null,
      ap: Number.isFinite(+ap[i]) ? Math.round(+ap[i]) : null, // round if you like
      f107: Number.isFinite(+f107[i]) ? +f107[i] : null,
      note: null,
      label: dates[i],
    });
  }
  return items;
}
