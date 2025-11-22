// src/components/ForecastTable.jsx
import React, { useMemo, useCallback, useRef } from "react";
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography, Paper, Box, Stack, Button, Tooltip
} from "@mui/material";
import dayjs from "dayjs";

// Integer Kp → Ap mapping (standard NOAA conversion)
function kpToAp(kpInt) {
  const map = { 0: 0, 1: 3, 2: 7, 3: 15, 4: 27, 5: 48, 6: 80, 7: 140, 8: 240, 9: 400 };
  return map[kpInt] ?? null;
}

// Safe CSV builder
function toCsv(rows, headers) {
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    const needsQuotes = /[",\n]/.test(s);
    return needsQuotes ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const headerLine = headers.map(h => esc(h.label)).join(",");
  const body = rows.map(r => headers.map(h => esc(r[h.key])).join(",")).join("\n");
  return headerLine + "\n" + body;
}

export default function ForecastTable({ items = [] }) {
  const containerRef = useRef(null);

  // Normalize & memoize rows (prevents re-renders on parent updates)
  const rows = useMemo(() => {
    return (items || []).map((row, idx) => {
      const kpNum = Number.isFinite(+row.kp) ? +row.kp : null;
      const apDerived = row.ap ?? (kpNum != null ? kpToAp(Math.round(kpNum)) : null);
      const f107 = row.f107 ?? row.f10_7 ?? null;
      const dateStr = row.date ? dayjs(row.date).format("YYYY-MM-DD") : `Day ${idx + 1}`;
      return {
        id: row.id ?? row.date ?? `r-${idx}`,
        date: dateStr,
        kp: kpNum,
        ap: apDerived,
        f107: f107,
        note: row.note ?? "",
      };
    });
  }, [items]);

  // CSV export handler
  const handleExportCsv = useCallback(() => {
    const headers = [
      { key: "date", label: "Date" },
      { key: "kp", label: "Kp" },
      { key: "ap", label: "Ap" },
      { key: "f107", label: "F10.7" },
      { key: "note", label: "Notes" },
    ];
    const csv = toCsv(rows, headers);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "forecast.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [rows]);

  return (
    <Box sx={{ width: "100%", display: "flex", justifyContent: "center", mt: 3 }}>
      <Stack sx={{ width: "100%" }} spacing={1}>
        <Stack direction="row" alignItems="center" justifyContent="flex-end">
          <Button variant="outlined" size="small" onClick={handleExportCsv}>
            ⬇️ Export CSV
          </Button>
        </Stack>

        <TableContainer
          ref={containerRef}
          component={Paper}
          sx={{
            width: "80% !important",              // keep your centered, narrow layout
            margin: "0 auto !important",
            backgroundColor: "rgba(255,255,255,0.04)",
            borderRadius: 3,
            boxShadow: "0 0 20px rgba(0,255,255,0.15)",
            backdropFilter: "blur(8px)",
            overflow: "auto",
            maxHeight: 520,                        // enables sticky header
            border: "1px solid rgba(0,229,255,0.25)",
          }}
        >
          <Table
            stickyHeader
            size="small"
            aria-label="27-day forecast table"
            sx={{
              "& thead th": {
                color: "#00e5ff",
                fontWeight: 700,
                backgroundColor: "rgba(255,255,255,0.02)",
                borderBottom: "1px solid rgba(255,255,255,0.08)",
              },
              "& td": { color: "#fff" },
              "& tbody tr:hover": { backgroundColor: "rgba(0,255,255,0.08)", transition: "0.25s ease" },
            }}
          >
            <TableHead>
              <TableRow>
                <TableCell>
                  <Typography variant="subtitle2">📅 Date</Typography>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Planetary K-index (0–9, geomagnetic activity)">
                    <Typography variant="subtitle2">🧭 Kp</Typography>
                  </Tooltip>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Ap index (derived from Kp)">
                    <Typography variant="subtitle2">📈 Ap</Typography>
                  </Tooltip>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Solar radio flux at 10.7 cm">
                    <Typography variant="subtitle2">☀️ F10.7</Typography>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <Typography variant="subtitle2">📝 Notes</Typography>
                </TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {rows.map((r) => {
                const kpBadgeBg =
                  r.kp == null ? "transparent" :
                  r.kp >= 7 ? "rgba(255,99,71,0.25)" :
                  r.kp >= 5 ? "rgba(255,165,0,0.18)" :
                  "rgba(255,255,255,0.06)";

                return (
                  <TableRow key={r.id} hover sx={{ "& td": { py: 1 } }}>
                    <TableCell>{r.date}</TableCell>

                    <TableCell align="right">
                      <Box
                        component="span"
                        sx={{
                          px: 1,
                          py: 0.25,
                          borderRadius: 1,
                          bgcolor: kpBadgeBg,
                          border: "1px solid rgba(255,255,255,0.08)",
                          display: "inline-block",
                          minWidth: 28,
                          textAlign: "right",
                        }}
                      >
                        {r.kp ?? "—"}
                      </Box>
                    </TableCell>

                    <TableCell align="right">{r.ap ?? "—"}</TableCell>
                    <TableCell align="right">{r.f107 ?? "—"}</TableCell>
                    <TableCell>{r.note}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>
    </Box>
  );
}
