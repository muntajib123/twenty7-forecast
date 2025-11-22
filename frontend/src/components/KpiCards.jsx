import { Grid, Card, CardContent, Typography } from '@mui/material'
export default function KpiCards({ kpis }){
  const items = [
    { label: 'Window', value: kpis.window },
    { label: 'Max Kp', value: kpis.kpMax },
    { label: 'Avg Kp', value: kpis.kpAvg },
    { label: 'Max Ap', value: kpis.apMax },
  ]
  return (
    <Grid container spacing={2}>
      {items.map(it=>(
        <Grid item xs={12} sm={6} md={3} key={it.label}>
          <Card><CardContent>
            <Typography variant="overline" sx={{ opacity: 0.8 }}>{it.label}</Typography>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>{it.value ?? '—'}</Typography>
          </CardContent></Card>
        </Grid>
      ))}
    </Grid>
  )
}
