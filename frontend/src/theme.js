// src/theme.js
import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#0047AB' }, // 💙 Strong blue for navbar & buttons
    secondary: { main: '#1E90FF' },
    background: {
      default: '#ffffff', // White background
      paper: '#f9fafc',   // Soft light gray for cards/tables
    },
    text: {
      primary: '#1a1a1a', // Dark text for white background
      secondary: '#4a4a4a',
    },
  },
  typography: {
    fontFamily: "'Poppins', 'Roboto', 'Helvetica', 'Arial', sans-serif",
    h5: { fontWeight: 700, letterSpacing: '0.8px' },
    subtitle2: { fontWeight: 600, fontSize: '0.9rem' },
    body2: { fontSize: '0.85rem' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 14 },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#0047AB', // ✅ Solid blue navbar
          color: '#ffffff',
          boxShadow: '0 3px 10px rgba(0,0,0,0.2)',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: '#ffffff',
          boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
          border: '1px solid #e0e0e0',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          fontWeight: 600,
          '&:hover': {
            backgroundColor: '#0056d6',
          },
        },
      },
    },
  },
});

export default theme;
