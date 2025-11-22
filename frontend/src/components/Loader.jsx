import { Stack, CircularProgress, Typography } from '@mui/material'
export default function Loader({ label='Loading...' }){
  return (
    <Stack direction="row" alignItems="center" spacing={2}>
      <CircularProgress size={22} />
      <Typography variant="body2">{label}</Typography>
    </Stack>
  )
}
