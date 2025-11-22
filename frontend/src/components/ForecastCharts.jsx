// src/components/ForecastCharts.jsx
import React, { useMemo, useRef, useCallback } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  Legend,
  ReferenceLine,
} from "recharts";
import { Box, Typography, Grid, Stack, Button } from "@mui/material";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";

/** ---------- helpers ---------- */
const num = (v) =>
  typeof v === "number"
    ? v
    : v === null || v === undefined || v === ""
    ? null
    : Number.isNaN(parseFloat(v))
    ? null
    : parseFloat(v);

const short = (s) => (typeof s === "string" ? s : String(s ?? ""))
  .replace(/^(\d{4}-\d{2}-\d{2}).*$/, "$1"); // trim ISO -> YYYY-MM-DD

const fmtNum = (v) => (v === null || v === undefined ? "—" : String(v));

/** Custom tooltip with units */
function Tip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const byKey = Object.fromEntries(payload.map((p) => [p.dataKey, p.value]));
  return (
    <Box
      sx={{
        p: 1.25,
        borderRadius: 1.5,
        bgcolor: "rgba(0,0,0,0.65)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      {"kp" in byKey && (
        <Typography variant="body2">Kp: {fmtNum(byKey.kp)}</Typography>
      )}
      {"ap" in byKey && (
        <Typography variant="body2">Ap: {fmtNum(byKey.ap)}</Typography>
      )}
      {"f107" in byKey && (
        <Typography variant="body2">F10.7: {fmtNum(byKey.f107)}</Typography>
      )}
    </Box>
  );
}

/** Simple, memoized card shell */
const Card = React.memo(function Card({ title, innerRef, children, onPng, onPdf }) {
  return (
    <Box
      sx={{
        height: { xs: 220, md: 240 },
        width: "100%",
        p: 2,
        borderRadius: 3,
        bgcolor: "rgba(255,255,255,0.04)",
        boxShadow: "0 0 16px rgba(0,255,255,0.12)",
        border: "1px solid rgba(110,231,255,0.25)",
      }}
      aria-label={title}
      role="region"
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Stack direction="row" spacing={1}>
          <Button size="small" variant="outlined" onClick={onPng}>
            📸 PNG
          </Button>
          <Button size="small" variant="outlined" onClick={onPdf}>
            📄 PDF
          </Button>
        </Stack>
      </Stack>
      <Box ref={innerRef} sx={{ height: "100%" }}>
        {children}
      </Box>
    </Box>
  );
});

function ForecastCharts({ items = [] }) {
  /** ---------- data shaping (memoized) ---------- */
  const data = useMemo(() => {
    if (!Array.isArray(items)) return [];
    return items.map((d, i) => ({
      label: short(d.label ?? d.date ?? `D${i + 1}`),
      kp: num(d.kp),
      ap: num(d.ap),
      f107: num(d.f107 ?? d.f10_7),
    }));
  }, [items]);

  // Keep Y domains stable so charts don’t “bounce” while data streams in.
  const kpDomain = useMemo(() => {
    const vals = data.map((d) => d.kp).filter((v) => v !== null);
    if (!vals.length) return [0, 9];
    const max = Math.max(...vals);
    return [0, Math.min(9, Math.max(6, Math.ceil(max)))];
  }, [data]);

  const apDomain = useMemo(() => {
    const vals = data.map((d) => d.ap).filter((v) => v !== null);
    if (!vals.length) return [0, 60];
    const max = Math.max(...vals);
    // Round up to nearest 10 for tidy grid.
    return [0, Math.max(40, Math.ceil(max / 10) * 10)];
  }, [data]);

  /** ---------- export handlers ---------- */
  const kpRef = useRef(null);
  const apRef = useRef(null);

  const exportPNG = useCallback(async (ref, filename) => {
    if (!ref?.current) return;
    const canvas = await html2canvas(ref.current, {
      scale: 2,
      backgroundColor: null,
      useCORS: true,
    });
    const link = document.createElement("a");
    link.download = filename;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }, []);

  const exportPDF = useCallback(async (ref, filename) => {
    if (!ref?.current) return;
    const canvas = await html2canvas(ref.current, {
      scale: 2,
      backgroundColor: "#ffffff",
      useCORS: true,
    });
    const img = canvas.toDataURL("image/png");
    const pdf = new jsPDF("landscape", "pt", "a4");
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 24;
    const w = pageW - margin * 2;
    const h = (canvas.height / canvas.width) * w;
    pdf.addImage(img, "PNG", margin, margin, w, Math.min(h, pageH - margin * 2));
    pdf.save(filename);
  }, []);

  /** ---------- render ---------- */
  return (
    <Grid container spacing={3} sx={{ width: "100%", mx: "auto" }}>
      {/* Kp Line */}
      <Grid item xs={12} md={8}>
        <Card
          title="Kp Index (Line)"
          innerRef={kpRef}
          onPng={() => exportPNG(kpRef, "kp_chart.png")}
          onPdf={() => exportPDF(kpRef, "kp_chart.pdf")}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 6, right: 14, left: 6, bottom: 6 }}>
              <defs>
                <linearGradient id="kpStroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#6ee7ff" />
                  <stop offset="100%" stopColor="#a78bfa" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.18} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                minTickGap={14}
                height={28}
              />
              <YAxis allowDecimals={false} domain={kpDomain} width={32} />
              <Tooltip content={<Tip />} />
              <Legend />
              {/* Helpful threshold guides */}
              <ReferenceLine y={4} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" />
              <ReferenceLine y={5} stroke="rgba(255,99,71,0.7)" strokeDasharray="6 6" />
              <ReferenceLine y={7} stroke="rgba(255,99,71,0.8)" strokeDasharray="2 8" />
              <Line
                type="monotone"
                dataKey="kp"
                name="Kp"
                dot={false}
                stroke="url(#kpStroke)"
                strokeWidth={2}
                isAnimationActive
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </Grid>

      {/* Ap Bar */}
      <Grid item xs={12} md={4}>
        <Card
          title="Ap Index (Bar)"
          innerRef={apRef}
          onPng={() => exportPNG(apRef, "ap_chart.png")}
          onPdf={() => exportPDF(apRef, "ap_chart.pdf")}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 6, right: 12, left: 6, bottom: 6 }}>
              <defs>
                <linearGradient id="apFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7ee8fa" />
                  <stop offset="100%" stopColor="#6ee7ff" stopOpacity="0.55" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.18} />
              <XAxis dataKey="label" hide />
              <YAxis allowDecimals={false} domain={apDomain} width={32} />
              <Tooltip content={<Tip />} />
              <Legend />
              <Bar dataKey="ap" name="Ap" fill="url(#apFill)" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </Grid>
    </Grid>
  );
}

export default React.memo(ForecastCharts);
