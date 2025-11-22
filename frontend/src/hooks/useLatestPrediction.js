import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLatestForecast } from '../api/client.js'
import { extractForecast } from '../utils/normalize.js'

export default function useLatestPrediction(){
  const [data,setData] = useState([])
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const abortRef = useRef(null)

  const load = useCallback(async ()=>{
    setLoading(true); setError('')
    abortRef.current?.abort?.()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try{
      const raw = await fetchLatestForecast(ctrl.signal)
      setData(extractForecast(raw))
    }catch(err){
      setError(err?.message || 'Failed to load latest forecast.')
    }finally{
      setLoading(false)
    }
  },[])

  useEffect(()=>{ load(); return ()=>abortRef.current?.abort?.() },[load])
  return { data, loading, error, refetch: load }
}
