// src/pages/PresentForecastPage.jsx
import React, { useEffect, useMemo, useState, useCallback } from "react";
import { Box, Stack, Typography, Paper, Grid, Card, CardContent, CardHeader, CircularProgress, Button, Alert } from "@mui/material";
import Header from "../components/Header";
import ForecastCharts from "../components/ForecastCharts";
import ForecastTable from "../components/ForecastTable";
import { normalize } from "../utils/normalize";

export default function PresentForecastPage() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const fetchForecast = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const res = await fetch("/api/noaa/27day/live");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setPayload(json);
    } catch (e) {
      setErr(e?.message || "Failed to load forecast.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchForecast(); }, [fetchForecast]);

  // Shape rows once (handles object payloads or arrays)
  const rows = useMemo(() => {
    if (!payload) return [];
    // Support both { days: [...] } and direct arrays/objects
    return normalize(payload?.days ?? payload);
  }, [payload]);

  // issued timestamp (optional)
  const issuedUtc = payload?.issued_utc || payload?.meta?.issued_utc || null;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header onRefresh={fetchForecast} />

      <Box sx={{ width: "100%", px: { xs: 1.5, sm: 2 }, py: 3 }}>
        <Stack spacing={2}>
          {loading && (
            <Paper sx={{ p: 2 }}>
              <Stack direction="row" alignItems="center" spacing={2}>
                <CircularProgress size={22} />
                <Typography>Loading 27-Day Forecast...</Typography>
              </Stack>
            </Paper>
          )}

          {err && (
            <Alert severity="error" sx={{ p: 2 }}>
              Error: {err}
            </Alert>
          )}

          {!loading && !err && (
            <>
              <Paper sx={{ p: 2 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      Present 27-Day Forecast
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.85 }}>
                      <b>Last Updated (UTC):</b> {issuedUtc || "N/A"}
                    </Typography>
                  </Box>
                  <Button size="small" variant="outlined" onClick={fetchForecast}>
                    Refresh
                  </Button>
                </Stack>
              </Paper>

              {/* Cards — first 27 days */}
              {rows?.length > 0 && (
                <Grid container spacing={2}>
                  {rows.slice(0, 27).map((d, i) => (
                    <Grid item xs={12} sm={6} md={4} lg={3} key={d.id ?? i}>
                      <Card
                        sx={{
                          height: "100%",
                          background: "rgba(255,255,255,0.04)",
                          border: "1px solid rgba(255,255,255,0.06)",
                          boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
                        }}
                      >
                        <CardHeader
                          title={`Day ${i + 1}`}
                          subheader={d.date ? d.date.slice(0, 10) : d.label}
                          sx={{ pb: 0 }}
                        />
                        <CardContent>
                          <Typography variant="body2"><b>Kp:</b> {d.kp ?? "—"}</Typography>
                          <Typography variant="body2"><b>Ap:</b> {d.ap ?? "—"}</Typography>
                          <Typography variant="body2"><b>F10.7:</b> {d.f107 ?? "—"}</Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              )}

              {/* Charts (polished component) */}
              <ForecastCharts items={rows} />

              {/* Table (sticky header + CSV) */}
              <ForecastTable items={rows} />
            </>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
