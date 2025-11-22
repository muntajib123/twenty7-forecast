import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import dayjs from "dayjs";
import {
  Box, Stack, Paper, Typography, Button, Alert, CircularProgress,
  Card, CardContent, CardHeader, Grid,
} from "@mui/material";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, BarChart, Bar
} from "recharts";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import Header from "./components/Header";
import HistoricalPage from "./pages/HistoricalPage"; // NEW import

// Read API base from Vite env. Falls back to localhost for dev.
const VITE_API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
// Ensure no trailing slash and add /api prefix
const API_BASE = VITE_API_BASE.replace(/\/$/, '') + '/api';

console.log('VITE_API_BASE_URL (build):', import.meta.env.VITE_API_BASE_URL);
console.log('API_BASE used by client:', API_BASE);

const NOAA_LATEST = "/noaa/27day/latest";
const NOAA_LIVE   = "/noaa/27day/live";
const PREDICT_TODAY  = "/predict/today";
const PREDICT_BEYOND = "/predict/beyond";

const PRESENT_LEN = 27;
const FUTURE_LEN  = 27;

export default function App() {
  const urlView = new URLSearchParams(window.location.search).get("view");
  const initialTab =
    urlView === "future" ? "future" : (urlView === "historical" ? "historical" : "present");
  const [tab, setTab] = useState(initialTab);

  const [present, setPresent] = useState(null);
  const [loadingPresent, setLoadingPresent] = useState(false);
  const [errPresent, setErrPresent] = useState("");

  const [future, setFuture] = useState(null);
  const [loadingFuture, setLoadingFuture] = useState(false);
  const [errFuture, setErrFuture] = useState("");

  const kpRef = useRef(null);
  const apRef = useRef(null);
  const fRef = useRef(null);
  const kpPresentRef = useRef(null);
  const apPresentRef = useRef(null);
  const fPresentRef = useRef(null);

  async function getJson(path) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`GET ${path} → ${res.status}${text ? `: ${text.slice(0, 200)}...` : ""}`);
    }
    const ct = res.headers.get("content-type") || "";
    const bodyText = await res.text();
    if (!ct.includes("application/json")) {
      const preview = bodyText.slice(0, 300);
      throw new Error(`Expected JSON but got content-type='${ct}'. Response start: ${preview}`);
    }
    try {
      return JSON.parse(bodyText);
    } catch (err) {
      throw new Error(`Invalid JSON from ${path}: ${err.message}. Response start: ${bodyText.slice(0,300)}`);
    }
  }

  async function getJsonWithFallback(paths) {
    let lastErr;
    for (const p of paths) {
      try { return await getJson(p); }
      catch (e) { lastErr = e; console.warn(`Fallback: ${p} failed →`, e.message); }
    }
    throw lastErr;
  }

  function toNum(v) {
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  function extractVal(x) {
    if (x == null) return null;
    if (typeof x === "object") return toNum(x.kp ?? x.value ?? x.pred ?? null);
    return toNum(x);
  }

  // PRESENT
  const fetchPresent = useCallback(async () => {
    setLoadingPresent(true);
    setErrPresent("");
    try {
      const noaa = await getJsonWithFallback([NOAA_LATEST, NOAA_LIVE]);
      const today = await getJson(PREDICT_TODAY);

      const days = Array.isArray(noaa?.days) ? noaa.days.slice(0, PRESENT_LEN) : [];
      const horizon = Array.isArray(today?.horizon) ? today.horizon.slice(0, PRESENT_LEN) : [];

      const merged = days.map((d, i) => ({
        date: d.date_utc ?? d.date ?? d.day ?? null,
        ap: toNum(d.ap ?? d.Ap),
        f107: toNum(d.f107 ?? d.f10_7 ?? d["f10.7"]),
        kp: extractVal(horizon[i]),
      }));

      setPresent(merged);
    } catch (e) {
      setErrPresent(String(e?.message || e));
    } finally {
      setLoadingPresent(false);
    }
  }, []);

  // FUTURE
  const fetchFuture = useCallback(async () => {
    setLoadingFuture(true);
    setErrFuture("");
    try {
      const noaa = await getJsonWithFallback([NOAA_LATEST, NOAA_LIVE]);
      const lastNoaaISO =
        Array.isArray(noaa?.days) && noaa.days.length
          ? (noaa.days[noaa.days.length - 1].date_utc ?? noaa.days[noaa.days.length - 1].date)
          : null;

      const start = dayjs(lastNoaaISO).isValid()
        ? dayjs(lastNoaaISO).add(1, "day")
        : dayjs().add(1, "day");

      try {
        // prefer trend mode if available
        const beyond = await getJson(`${PREDICT_BEYOND}?mode=trend`);
        const kpH = Array.isArray(beyond?.horizon) ? beyond.horizon.slice(0, FUTURE_LEN) : [];
        const apH =
          Array.isArray(beyond?.ap_horizon) ? beyond.ap_horizon.slice(0, FUTURE_LEN)
          : Array.isArray(beyond?.ap) ? beyond.ap.slice(0, FUTURE_LEN)
          : [];
        const fH =
          Array.isArray(beyond?.f107_horizon) ? beyond.f107_horizon.slice(0, FUTURE_LEN)
          : Array.isArray(beyond?.f10_7) ? beyond.f10_7.slice(0, FUTURE_LEN)
          : [];

        if (!kpH.length) throw new Error("Future endpoint returned empty horizon.");

        const rows = Array.from({ length: FUTURE_LEN }, (_, i) => ({
          date: start.add(i, "day").toISOString(),
          kp: extractVal(kpH[i]),
          ap: extractVal(apH[i]),
          f107: extractVal(fH[i]),
        }));

        setFuture(rows);
      } catch (errBeyond) {
        console.warn("predict/beyond failed; using fallback from /predict/today:", errBeyond.message);

        const today = await getJson(PREDICT_TODAY);
        const horizon = Array.isArray(today?.horizon) ? today.horizon.slice(0, FUTURE_LEN) : [];
        if (!horizon.length) throw new Error("No fallback horizon available.");

        const rows = Array.from({ length: FUTURE_LEN }, (_, i) => ({
          date: start.add(i, "day").toISOString(),
          kp: extractVal(horizon[i]),
          ap: null,
          f107: null,
        }));

        setFuture(rows);
      }
    } catch (e) {
      setErrFuture(String(e?.message || e));
    } finally {
      setLoadingFuture(false);
    }
  }, []);

  useEffect(() => { fetchPresent(); fetchFuture(); }, [fetchPresent, fetchFuture]);

  const chartDataPresent = useMemo(() => {
    if (!present) return [];
    return present.map((d) => ({ date: fmtDate(d.date), kp: toNum(d.kp), ap: toNum(d.ap), f107: toNum(d.f107) }));
  }, [present]);

  const chartDataFuture = useMemo(() => {
    if (!future) return [];
    return future.map((d) => ({ label: fmtDate(d.date), kp: toNum(d.kp), ap: toNum(d.ap), f107: toNum(d.f107) }));
  }, [future]);

  const exportPNG = async (node, filename) => {
    if (!node) return;
    const canvas = await html2canvas(node, { scale: 2, backgroundColor: "#ffffff" });
    const link = document.createElement("a");
    link.download = filename;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  const exportPDF = async (node, filename) => {
    if (!node) return;
    const canvas = await html2canvas(node, { scale: 2, backgroundColor: "#ffffff" });
    const img = canvas.toDataURL("image/png");
    const pdf = new jsPDF("landscape", "pt", "a4");
    const pageW = pdf.internal.pageSize.getWidth();
    const margin = 24;
    const w = pageW - margin * 2;
    const h = (canvas.height / canvas.width) * w;
    pdf.addImage(img, "PNG", margin, margin, w, h);
    pdf.save(filename);
  };

  return (
    <Box sx={{ minHeight: "100vh", backgroundColor: "#fff" }}>
      <Header tab={tab} onChangeView={setTab} onRefresh={tab === "future" ? fetchFuture : fetchPresent} />

      <Box sx={{ width: "100%", px: 2, py: 2 }}>
        {tab === "present" ? (
          <PresentView
            loading={loadingPresent}
            error={errPresent}
            data={present}
            chartData={chartDataPresent}
            refs={{ kpPresentRef, apPresentRef, fPresentRef }}
            exportPNG={exportPNG}
            exportPDF={exportPDF}
            onRetry={fetchPresent}
          />
        ) : tab === "future" ? (
          <FutureView
            loading={loadingFuture}
            error={errFuture}
            data={future}
            chartData={chartDataFuture}
            refs={{ kpRef, apRef, fRef }}
            exportPNG={exportPNG}
            exportPDF={exportPDF}
            onRetry={fetchFuture}
          />
        ) : (
          <HistoricalPage />
        )}
      </Box>
    </Box>
  );
}

/* ===== Helpers & Subcomponents ===== */
function fmtDate(d) {
  if (!d) return "—";
  const t = dayjs(d);
  return t.isValid() ? t.format("YYYY-MM-DD") : String(d);
}
function fmt(v) { return v == null ? "—" : v; }

function LoadingBlock({ text }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <CircularProgress size={22} />
        <Typography>{text}</Typography>
      </Stack>
    </Paper>
  );
}

function ErrorBlock({ text, onRetry }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Alert severity="error" sx={{ flexGrow: 1 }}>{text}</Alert>
        <Button variant="outlined" onClick={onRetry}>Retry</Button>
      </Stack>
    </Paper>
  );
}

function ForecastCards({ data }) {
  return (
    <Grid container spacing={2}>
      {data.map((d, i) => (
        <Grid item xs={12} sm={6} md={4} lg={3} key={`${d.date ?? "d"}-${i}`}>
          <Card sx={{ height: "100%", background: "rgba(255,255,255,0.9)", border: "1px solid rgba(0,0,0,0.1)", boxShadow: "0 2px 6px rgba(0,0,0,0.1)" }}>
            <CardHeader title={`Day ${i + 1}`} subheader={fmtDate(d.date)} sx={{ pb: 0 }} />
            <CardContent>
              <Typography variant="body2"><b>Kp:</b> {fmt(d.kp)}</Typography>
              <Typography variant="body2"><b>Ap:</b> {fmt(d.ap)}</Typography>
              <Typography variant="body2"><b>F10.7:</b> {fmt(d.f107)}</Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

const ForecastChart = ({ type, title, refProp, data, dataKey, color, exportPNG, exportPDF }) => (
  <Paper sx={{ p: 2, width: "90%", mx: "auto", background: "#f8f9fb", boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "#001f3f" }}>{title}</Typography>
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="outlined" onClick={() => exportPNG(refProp.current, `${dataKey}.png`)}>PNG</Button>
        <Button size="small" variant="outlined" onClick={() => exportPDF(refProp.current, `${dataKey}.pdf`)}>PDF</Button>
      </Stack>
    </Stack>
    <Box ref={refProp} sx={{ height: 300, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        {type === "bar" ? (
          <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
            <XAxis dataKey={"label" in (data[0] || {}) ? "label" : "date"} tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey={dataKey} fill={color} barSize={16} />
          </BarChart>
        ) : (
          <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
            <XAxis dataKey={"label" in (data[0] || {}) ? "label" : "date"} tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </Box>
  </Paper>
);

function PresentView({ loading, error, data, chartData, refs, exportPNG, exportPDF, onRetry }) {
  const { kpPresentRef, apPresentRef, fPresentRef } = refs;
  return (
    <Stack spacing={2}>
      {loading && <LoadingBlock text="Loading Present 27-Day Forecast..." />}
      {error && <ErrorBlock text={error} onRetry={onRetry} />}
      {data?.length > 0 && <ForecastCards data={data} />}
      {data?.length > 0 && (
        <>
          <ForecastChart type="line" title="Kp Index Trend" refProp={kpPresentRef} data={chartData} dataKey="kp" color="#007bff" exportPNG={exportPNG} exportPDF={exportPDF} />
          <ForecastChart type="bar" title="Ap Index" refProp={apPresentRef} data={chartData} dataKey="ap" color="#004aad" exportPNG={exportPNG} exportPDF={exportPDF} />
          <ForecastChart type="line" title="Radio Flux (F10.7)" refProp={fPresentRef} data={chartData} dataKey="f107" color="#00b4d8" exportPNG={exportPNG} exportPDF={exportPDF} />
        </>
      )}
    </Stack>
  );
}

function FutureView({ loading, error, data, chartData, refs, exportPNG, exportPDF, onRetry }) {
  const { kpRef, apRef, fRef } = refs;
  return (
    <Stack spacing={2}>
      {loading && <LoadingBlock text={`Fetching next ${FUTURE_LEN} days…`} />}
      {error && <ErrorBlock text={error} onRetry={onRetry} />}
      {data?.length > 0 && <ForecastCards data={data} />}
      {data?.length > 0 && (
        <>
          <ForecastChart type="line" title="Kp Index" refProp={kpRef} data={chartData} dataKey="kp" color="#007bff" exportPNG={exportPNG} exportPDF={exportPDF} />
          <ForecastChart type="bar" title="Ap Index" refProp={apRef} data={chartData} dataKey="ap" color="#004aad" exportPNG={exportPNG} exportPDF={exportPDF} />
          <ForecastChart type="line" title="Radio Flux (F10.7)" refProp={fRef} data={chartData} dataKey="f107" color="#00b4d8" exportPNG={exportPNG} exportPDF={exportPDF} />
        </>
      )}
    </Stack>
  );
}
