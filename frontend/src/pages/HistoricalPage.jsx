// frontend/src/pages/HistoricalPage.jsx
// Uploaded raw file (for your reference): /mnt/data/c8797b69-131f-4cfb-8eab-9296b66163ef.txt

import React, { useEffect, useState } from "react";
import {
  Box, Button, TextField, Stack, Paper,
  Grid, Card, CardContent, Typography
} from "@mui/material";

// Same API base as App.jsx
const API_BASE = "http://localhost:8000/api";

function formatVal(v) {
  if (v == null) return "—";
  return Number.isInteger(v) ? String(v) : String(Number(v).toFixed(2));
}

export default function HistoricalPage() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function load(startDate, endDate) {
    setLoading(true);
    setErr("");

    try {
      const params = new URLSearchParams();
      if (startDate) params.append("start", startDate);
      if (endDate) params.append("end", endDate);

      const url = `${API_BASE}/historical${params.toString() ? "?" + params.toString() : ""}`;
      const res = await fetch(url);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setErr(String(e?.message || e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <Box sx={{ p: 3 }}>

      {/* Correct heading */}
      <Typography
        variant="h5"
        sx={{
          mb: 2,
          fontWeight: 700,
          textAlign: "center",
          letterSpacing: 0.5
        }}
      >
        Historical 27-Day
      </Typography>

      {/* Filter Box */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems="center"
          justifyContent="center"
        >
          <TextField
            label="Start (YYYY-MM-DD)"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            size="small"
          />

          <TextField
            label="End (YYYY-MM-DD)"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            size="small"
          />

          <Button
            variant="contained"
            onClick={() => load(start, end)}
            disabled={loading}
          >
            Filter
          </Button>

          <Button
            variant="outlined"
            onClick={() => {
              const params = new URLSearchParams();
              if (start) params.append("start", start);
              if (end) params.append("end", end);
              window.location.href = `${API_BASE}/historical?${params.toString()}&format=csv`;
            }}
          >
            Download CSV
          </Button>
        </Stack>
      </Paper>

      {/* Errors */}
      {err && (
        <Typography color="error" sx={{ mb: 2, textAlign: "center" }}>
          {err}
        </Typography>
      )}

      {/* Card Grid */}
      <Grid container spacing={2}>
        {rows.map((r) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={r.date}>
            <Card sx={{
              height: "100%",
              borderRadius: 2,
              boxShadow: "0 6px 18px rgba(2,6,23,0.06)"
            }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
                  {r.date}
                </Typography>
                <Stack spacing={0.5}>
                  <Typography variant="body2"><strong>F10.7:</strong> {formatVal(r.f107)}</Typography>
                  <Typography variant="body2"><strong>Ap:</strong> {formatVal(r.ap)}</Typography>
                  <Typography variant="body2"><strong>Kp:</strong> {formatVal(r.kp)}</Typography>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {!loading && rows.length === 0 && !err && (
        <Typography sx={{ mt: 3, textAlign: "center" }}>
          No rows to show (try removing filters).
        </Typography>
      )}
    </Box>
  );
}
