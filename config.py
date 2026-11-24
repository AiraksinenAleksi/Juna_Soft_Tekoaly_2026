"""Central configuration — tune via environment variables, no logic here."""
import os

BASE = "https://rata.digitraffic.fi/api/v1"

DIGITRAFFIC_USER = os.environ.get("DIGITRAFFIC_USER", "my-railway-app.example.com")
DEBUG = os.environ.get("FLASK_DEBUG") == "1"

REQUEST_TIMEOUT = 15          # seconds for upstream calls
STATION_TTL = 3600            # station list cache: 1 hour
LIVE_TTL = 45                 # live departures cache: 45 s (shared per station)

# Departure-board window, as the API's minute-window variant expects:
MINUTES_BEFORE_DEPARTURE = 15
MINUTES_AFTER_DEPARTURE = 120
MINUTES_BEFORE_ARRIVAL = 0
MINUTES_AFTER_ARRIVAL = 0