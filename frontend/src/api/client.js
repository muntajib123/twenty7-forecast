import axios from 'axios'

// ✅ Base URL setup
// - In development, Vite proxy allows using '/api' (see vite.config.js).
// - In production (e.g. Vercel + Render backend), set VITE_API_BASE_URL in .env to your Render API URL.
const BASE = import.meta.env.VITE_API_BASE_URL || '/api'

/**
 * Fetches the 27-day future forecast (beyond NOAA’s range).
 * NOAA current ends on Nov 2 → this starts from Nov 3 automatically.
 * Mode can be 'mean7' (average of last 7 days) or 'hold' (repeat last day).
 */
export async function fetchLatestForecast(signal) {
  try {
    // ✅ Use /predict/beyond to get future forecast window (e.g. Nov 3 → Nov 29)
    const res = await axios.get(`${BASE}/predict/beyond?mode=mean7`, { signal })
    return res.data
  } catch (err) {
    console.error('❌ Failed to fetch forecast:', err)
    throw new Error(
      err?.response?.data?.detail || 'Failed to fetch future 27-day forecast.'
    )
  }
}

/**
 * Optional: fallback to latest saved prediction if beyond API fails.
 * You can call this separately if you want a retry fallback.
 */
export async function fetchLatestSaved(signal) {
  try {
    const res = await axios.get(`${BASE}/predictions/latest`, { signal })
    return res.data
  } catch (err) {
    console.warn('⚠️ Falling back to latest saved prediction:', err)
    throw new Error('No saved prediction available.')
  }
}
