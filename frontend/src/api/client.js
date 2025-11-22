import axios from "axios";

// Use Vercel build-time env when available, otherwise fall back to /api (dev)
const API_ROOT = import.meta.env.VITE_API_BASE_URL || "";
const BASE = API_ROOT ? `${API_ROOT}/api` : "/api";

// Fetch future 27-day forecast
export async function fetchLatestForecast(signal) {
  try {
    const res = await axios.get(`${BASE}/predict/beyond?mode=mean7`, { signal });
    return res.data;
  } catch (err) {
    console.error("❌ Failed to fetch forecast:", err);
    throw new Error(err?.response?.data?.detail || "Failed to fetch future 27-day forecast.");
  }
}

export async function fetchLatestSaved(signal) {
  try {
    const res = await axios.get(`${BASE}/predictions/latest`, { signal });
    return res.data;
  } catch (err) {
    console.warn("⚠️ No saved prediction available:", err);
    throw new Error("No saved prediction available.");
  }
}
