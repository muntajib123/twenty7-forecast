import { Alert, Button, Stack } from '@mui/material'
export default function ErrorState({ message, onRetry }){
  return (
    <Stack direction="row" alignItems="center" spacing={2}>
      <Alert severity="error" sx={{ flexGrow: 1 }}>{message || 'Something went wrong.'}</Alert>
      {onRetry ? <Button variant="outlined" onClick={onRetry}>Retry</Button> : null}
    </Stack>
  )
}
