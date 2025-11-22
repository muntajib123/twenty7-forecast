// src/components/PresentFutureCards.jsx
import React, { useEffect, useMemo, useState } from "react";
import {
  Box, Grid, Card, CardContent, Typography, CircularProgress, Alert, Button, Stack
} from "@mui/material";

const API = "http://localhost:8000";

/** normalize Kp from number or { kp } */
function pickKp(val) {
  if (val == null) return null;
  if (typeof val === "number") return val;
  if (typeof val === "object" && "kp" in val) return val.kp;
  return Number(val);
}

/** integer Kp -> Ap mapping (NOAA standard) */
function kpToAp(kpInt) {
  const map = { 0: 0, 1: 3, 2: 7, 3: 15, 4: 27, 5: 48, 6: 80, 7: 140, 8: 240, 9: 400 };
  return map[kpInt] ?? null;
}

function HSectionTitle({ title, sub }) {
  return (
    <Box mb={1}>
      <Typography variant="h5" fontWeight={700}>{title}</Typography>
      {sub ? <Typography variant="body2" sx={{ opacity: 0.8 }}>{sub}</Typography> : null}
    </Box>
  );
}

function KPCard({ title, date, ap, f107, kp }) {
  return (
    <Card sx={{ borderRadius: 3, height: "100%", bgcolor: "rgba(255,255,255,0.02)", backdropFilter: "blur(2px)" }}>
      <CardContent>
        <Typography variant="subtitle2" sx={{ opacity: 0.8 }}>{title}</Typography>
        <Typography variant="h6" sx={{ mb: 1 }}>{date || "—"}</Typography>
        <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
          <Box>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>Ap</Typography>
            <Typography variant="body1">{ap ?? "—"}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>F10.7</Typography>
            <Typography variant="body1">{f107 ?? "—"}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>Kp</Typography>
            <Typography variant="body1">{kp ?? "—"}</Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function PresentFutureCards() {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  // raw payloads
  const [noaa, setNoaa] = useState(null);          // /noaa/27day/latest
  const [todayPred, setTodayPred] = useState(null); // /predict/today
  const [beyond, setBeyond] = useState(null);       // /predict/beyond

  const getJson = async (url, signal) => {
    const r = await fetch(url, { signal });
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  };

  const fetchAll = async (abort) => {
    setErr(null);
    setLoading(true);
    try {
      const [a, b, c] = await Promise.all([
        getJson(`${API}/noaa/27day/latest`, abort?.signal).catch(() => null),
        getJson(`${API}/predict/today`, abort?.signal).catch(() => null),
        getJson(`${API}/predict/beyond`, abort?.signal).catch(() => null),
      ]);
      setNoaa(a);
      setTodayPred(b);
      setBeyond(c);
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const abort = new AbortController();
    fetchAll(abort);
    return () => abort.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** ---------- PRESENT (27 only) ---------- */
  const presentCards = useMemo(() => {
    const days = Array.isArray(noaa?.days) ? noaa.days : [];
    const horizon = Array.isArray(todayPred?.horizon) ? todayPred.horizon : [];
    return days.slice(0, 27).map((d, i) => {
      const date = d?.date_utc ?? d?.date ?? d?.day ?? null;
      const ap = d?.ap ?? d?.Ap ?? null;
      const f107 = d?.f107 ?? d?.f10_7 ?? d?.["f10.7"] ?? null;
      // if model horizon exists, use it; otherwise prefer NOAA kp if present
      const kpFromModel = (Array.isArray(horizon) && (horizon[i] != null)) ? pickKp(horizon[i]) : null;
      const kpFromNoaa = (d && ("kp" in d)) ? pickKp(d.kp) : null;
      const kp = kpFromModel ?? kpFromNoaa ?? null;
      return { date, ap, f107, kp };
    });
  }, [noaa, todayPred]);

  /** ---------- FUTURE (27 only) ----------
   * Use beyond.horizon (Kp), beyond.ap_horizon (Ap) and beyond.f107_horizon (F10.7)
   * If any series missing, fallback sensibly.
   */
  const futureCards = useMemo(() => {
    if (!beyond) return [];
    const dates = Array.isArray(beyond.dates_utc) ? beyond.dates_utc : [];
    const kpSeries = Array.isArray(beyond.horizon) ? beyond.horizon : [];
    const apSeries = Array.isArray(beyond.ap_horizon) ? beyond.ap_horizon : [];
    const f107Series = Array.isArray(beyond.f107_horizon) ? beyond.f107_horizon : [];

    const len = Math.min(27, Math.max(dates.length, kpSeries.length, apSeries.length, f107Series.length));
    return Array.from({ length: len }, (_, i) => {
      const date = dates[i] ?? null;

      // Kp: prefer model horizon value, else null
      const rawKp = kpSeries[i] != null ? kpSeries[i] : null;
      // Normalize Kp to number or null
      const kp = rawKp == null ? null : Number(rawKp);

      // Ap: prefer apSeries (from feature extender). If missing, derive from rounded kp.
      let ap = (apSeries[i] != null) ? Number(apSeries[i]) : null;
      if ((ap === null || Number.isNaN(ap)) && kp != null) {
        ap = kpToAp(Math.round(kp));
      }

      // F10.7: prefer series value else null
      const f107 = (f107Series[i] != null) ? Number(f107Series[i]) : null;

      return { date, ap, f107, kp };
    });
  }, [beyond]);

  const presentEmpty =
    presentCards.length === 0 ||
    presentCards.every(x => x.date == null && x.ap == null && x.f107 == null && x.kp == null);

  const futureEmpty =
    futureCards.length === 0 ||
    futureCards.every(x => x.date == null && x.kp == null && x.ap == null && x.f107 == null);

  /** Repair helper */
  const handleRepair = async () => {
    setErr(null);
    setLoading(true);
    try {
      await fetch(`${API}/noaa/27day/sync`, { method: "POST" }).catch(() => null);
      await fetch(`${API}/cron/run-now`, { method: "POST" }).catch(() => null);
      const abort = new AbortController();
      await fetchAll(abort);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      {loading && (
        <Box py={4} display="flex" alignItems="center" justifyContent="center">
          <CircularProgress />
        </Box>
      )}

      {!loading && err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {/* PRESENT */}
      <HSectionTitle title="Present (27 days)" sub="NOAA window: Dates/AP/F10.7 + predicted Kp" />
      {presentEmpty ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Present data looks empty. Try “Repair”.
          <Button onClick={handleRepair} sx={{ ml: 2 }} variant="outlined">Repair</Button>
        </Alert>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 4 }}>
        {presentCards.map((row, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={`present-${idx}`}>
            <KPCard title={`Day ${idx + 1}`} date={row.date} ap={row.ap} f107={row.f107} kp={row.kp} />
          </Grid>
        ))}
      </Grid>

      {/* FUTURE */}
      <HSectionTitle title="Future (next 27 days)" sub="Starts day after NOAA window: predicted Kp, Ap & F10.7 (when available)" />
      {futureEmpty ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Future data looks empty. If you just synced, try Repair.
          <Button onClick={handleRepair} sx={{ ml: 2 }} variant="outlined">Repair</Button>
        </Alert>
      ) : null}

      <Grid container spacing={2}>
        {futureCards.map((row, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={`future-${idx}`}>
            <KPCard title={`+${idx + 1} day`} date={row.date} ap={row.ap} f107={row.f107} kp={row.kp} />
          </Grid>
        ))}
      </Grid>

      {/* diagnostics */}
      <Box mt={3} sx={{ opacity: 0.7 }}>
        <Typography variant="caption">
          Debug: present={presentCards.length} future={futureCards.length}
        </Typography>
      </Box>
    </Box>
  );
}
