import { AppBar, Toolbar, Typography, Button, Box, Container } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import coralcompLogo from "../assets/coralcomp.png";

export default function Header({ onRefresh = () => {}, tab, onChangeView }) {
  return (
    <AppBar
      position="sticky"
      elevation={4}
      sx={{
        top: 0,
        zIndex: 1200,
        backgroundColor: "#001f3f",
        boxShadow: "0 4px 15px rgba(0,0,0,0.4)",
      }}
    >
      <Container maxWidth="lg">
        <Toolbar
          disableGutters
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            py: 1.5,
            flexWrap: "nowrap",
            position: "relative",
          }}
        >
          {/* Left side: Logo */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <img
              src={coralcompLogo}
              alt="CoralComp"
              style={{
                width: 45,
                height: 45,
                objectFit: "contain",
                borderRadius: "6px",
                backgroundColor: "transparent",
              }}
            />
          </Box>

          {/* Center: Title */}
          <Typography
            variant="h5"
            sx={{
              position: "absolute",
              left: "50%",
              transform: "translateX(-50%)",
              fontWeight: 800,
              color: "#fff",
              letterSpacing: "0.8px",
              textShadow: "0 0 4px rgba(255,255,255,0.2)",
              fontSize: { xs: "1.3rem", sm: "1.6rem", md: "1.9rem" },
              lineHeight: 1.2,
              userSelect: "none",
              whiteSpace: "nowrap",
            }}
          >
            27-Day Space Forecast
          </Typography>

          {/* Right side: Refresh */}
          <Button
            onClick={onRefresh}
            variant="contained"
            startIcon={<RefreshIcon />}
            aria-label="Refresh forecast"
            sx={{
              backgroundColor: "#0059b3",
              color: "#fff",
              fontWeight: 700,
              textTransform: "none",
              borderRadius: 3,
              px: 3,
              py: 1,
              "&:hover": {
                backgroundColor: "#0073e6",
                boxShadow: "0 0 10px rgba(0,115,230,0.4)",
              },
            }}
          >
            Refresh
          </Button>
        </Toolbar>
      </Container>

      {/* Buttons below header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 2,
          py: 1.5,
          backgroundColor: "#f9f9f9",
          boxShadow: "inset 0 1px 3px rgba(0,0,0,0.1)",
        }}
      >
        <Button
          variant={tab === "present" ? "outlined" : "contained"}
          onClick={() => onChangeView("present")}
          sx={{
            fontWeight: 700,
            textTransform: "none",
            px: 3,
            py: 1,
            borderRadius: 2,
          }}
        >
          Present 27-Day
        </Button>
        <Button
          variant={tab === "future" ? "contained" : "outlined"}
          onClick={() => onChangeView("future")}
          sx={{
            fontWeight: 700,
            textTransform: "none",
            px: 3,
            py: 1,
            borderRadius: 2,
          }}
        >
          Future 27-Day
        </Button>

        {/* NEW: Historical button */}
        <Button
          variant={tab === "historical" ? "contained" : "outlined"}
          onClick={() => onChangeView("historical")}
          sx={{
            fontWeight: 700,
            textTransform: "none",
            px: 3,
            py: 1,
            borderRadius: 2,
          }}
        >
          Historical Data
        </Button>
      </Box>
    </AppBar>
  );
}
