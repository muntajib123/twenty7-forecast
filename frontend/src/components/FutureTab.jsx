// src/components/FutureTab.jsx
import React, { useEffect, useState } from "react";
import { Box, Stack, Button } from "@mui/material";
// ⬇️ Removed ForecastTable import
import ForecastCharts from "./ForecastCharts";
import { fetchLatestForecast } from "../api/client";
import { extractForecast } from "../utils/extractForecast";

export default function FutureTab() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    (async () => {
      const payload = await fetchLatestForecast();
      const rows = extractForecast(payload) || [];
      setItems(rows);
      console.log("[FutureTab] items sample:", rows.slice(0, 3));
    })();
  }, []);

  // Hard-cap to 27 so there is never a “Day 28”
  const items27 = Array.isArray(items) ? items.slice(0, 27) : [];

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", px: 2, pb: 4 }}>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
        <Button size="small" variant="outlined" onClick={() => window.location.reload()}>
          Refresh
        </Button>
      </Stack>

      {/* Charts only (no table), fed with 27 items max */}
      <ForecastCharts items={items27} />
    </Box>
  );
}
