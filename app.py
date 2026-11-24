import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from config import (
    BASE, DIGITRAFFIC_USER, DEBUG, REQUEST_TIMEOUT,
    STATION_TTL, LIVE_TTL,
    MINUTES_BEFORE_DEPARTURE, MINUTES_AFTER_DEPARTURE,
    MINUTES_BEFORE_ARRIVAL, MINUTES_AFTER_ARRIVAL,
)

app = Flask(__name__)
HEADERS = {"Digitraffic-User": DIGITRAFFIC_USER}
HELSINKI = ZoneInfo("Europe/Helsinki")

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

GENERIC_ERROR = "Live train data is temporarily unavailable. Please try again shortly."


# ---------------- upstream access ----------------

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------------- caching ----------------

_STATION_CACHE = {"data": None, "map": None, "ts": 0.0}
_LIVE_CACHE = {}   # station code -> {"rows": [...], "error": str|None, "ts": float}


def _load_passenger_stations():
    stations = fetch(f"{BASE}/metadata/stations")
    return sorted(
        (s for s in stations
         if s.get("passengerTraffic") and not s.get("deleted")),
        key=lambda s: s["stationName"].lower(),
    )


def get_passenger_stations(allow_stale=True):
    """
    Cached station list. On refresh failure serves stale data if available;
    with allow_stale=False it raises instead (used to validate new codes).
    """
    now = time.monotonic()
    has_data = _STATION_CACHE["data"] is not None
    expired = not has_data or (now - _STATION_CACHE["ts"]) > STATION_TTL

    if expired:
        try:
            data = _load_passenger_stations()
            _STATION_CACHE["data"] = data
            _STATION_CACHE["map"] = {s["stationShortCode"]: s["stationName"] for s in data}
            _STATION_CACHE["ts"] = now
        except requests.RequestException:
            if allow_stale and has_data:
                logger.exception("Station refresh failed; serving stale cache")
            else:
                raise
    return _STATION_CACHE["data"]


def station_name(code):
    return (_STATION_CACHE["map"] or {}).get(code, code)


# ---------------- parsing (pure, testable) ----------------

def parse_iso(iso_str):
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def fmt_time(dt, today=None):
    """HH:MM in Helsinki; prefixes the date when it's not today."""
    local = dt.astimezone(HELSINKI)
    today = today or datetime.now(HELSINKI).date()
    hm = local.strftime("%H:%M")
    if local.date() != today:
        return f"{local.strftime('%d.%m.')} {hm}"
    return hm


def train_row(train, station_code, today=None):
    """
    Build one display row defensively; returns None for unusable records.
    Treats upstream data as always slightly wrong: required fields are
    checked, non-stopping departures are skipped.
    """
    rows = train.get("timeTableRows")
    if not isinstance(rows, list):
        return None

    dep = next(
        (r for r in rows
         if r.get("type") == "DEPARTURE"
         and r.get("stationShortCode") == station_code
         and r.get("commercialStop") is not False),
        None,
    )
    if dep is None:
        return None

    try:
        scheduled_dt = parse_iso(dep["scheduledTime"])
    except (KeyError, TypeError, ValueError):
        return None

    if dep.get("liveEstimateTime"):
        try:
            live_dt = parse_iso(dep["liveEstimateTime"])
            # Minute-truncated, like fmt_time()'s HH:MM display below — so the
            # "Late N min" badge always agrees with what the two time columns
            # visibly show, instead of rounding the raw (sub-minute) seconds
            # difference and occasionally landing a minute off from the display.
            sched_minute = scheduled_dt.replace(second=0, microsecond=0)
            live_minute = live_dt.replace(second=0, microsecond=0)
            delay_min = int((live_minute - sched_minute).total_seconds() // 60)
        except (TypeError, ValueError):
            live_dt, delay_min = scheduled_dt, None
    else:
        live_dt, delay_min = scheduled_dt, None

    arrivals = [
        r.get("stationShortCode") for r in rows
        if r.get("type") == "ARRIVAL" and r.get("commercialStop")
           and r.get("stationShortCode")
    ]
    destination_code = arrivals[-1] if arrivals else None

    category = train.get("trainCategory") or ""
    number = train.get("trainNumber")
    label = f"{category} {number}".strip() if number is not None else category
    cancelled = bool(dep.get("cancelled"))

    if cancelled:
        status = "cancelled"
    elif delay_min and delay_min > 10:
        status = "critical"
    elif delay_min and delay_min > 0:
        status = "warning"
    else:
        status = "good"

    return {
        "train": label,
        "category": category,
        "commuter_line": train.get("commuterLineID"),
        "destination_code": destination_code,
        "destination": station_name(destination_code) if destination_code else "?",
        "scheduled_dt": scheduled_dt.isoformat(),     # for sorting / JSON
        "scheduled": fmt_time(scheduled_dt, today),
        "live": fmt_time(live_dt, today),
        "delay_min": delay_min,
        "cancelled": cancelled,
        "status": status,
        "track": dep.get("commercialTrack") or "",
    }


def parse_departures(data, station_code):
    """Deduplicate, drop unusable rows, sort by real timestamp (midnight-safe)."""
    today = datetime.now(HELSINKI).date()
    parsed, seen = [], set()
    for t in data:
        try:
            row = train_row(t, station_code, today)
        except Exception:               # never let one bad record 500 the page
            logger.warning("Unparsable train record for %s", station_code, exc_info=True)
            continue
        if not row:
            continue
        key = (row["train"], row["scheduled_dt"])
        if key not in seen:
            seen.add(key)
            parsed.append(row)
    parsed.sort(key=lambda r: r["scheduled_dt"])
    for r in parsed:
        del r["scheduled_dt"]           # internal field; keep templates clean
    return parsed


def live_departures(code, force=False):
    """
    Cached live departures per station. Shared across users hitting the
    same station; serves stale data on upstream failure.
    """
    now = time.monotonic()
    entry = _LIVE_CACHE.get(code)
    if force or entry is None or (now - entry["ts"]) > LIVE_TTL:
        url = (
            f"{BASE}/live-trains/station/{code}"
            f"?minutes_before_departure={MINUTES_BEFORE_DEPARTURE}"
            f"&minutes_after_departure={MINUTES_AFTER_DEPARTURE}"
            f"&minutes_before_arrival={MINUTES_BEFORE_ARRIVAL}"
            f"&minutes_after_arrival={MINUTES_AFTER_ARRIVAL}"
            "&include_nonstopping=false"
        )
        try:
            data = fetch(url)
            _LIVE_CACHE[code] = {"rows": parse_departures(data, code),
                                 "error": None, "ts": now}
        except requests.RequestException:
            logger.exception("Live data request failed for station %s", code)
            if entry is not None:
                entry["error"] = GENERIC_ERROR + " (showing recent data)"
                entry["ts"] = now          # back off before the next attempt
            else:
                _LIVE_CACHE[code] = {"rows": [], "error": GENERIC_ERROR, "ts": now}
    return _LIVE_CACHE[code]


# ---------------- security headers ----------------

@app.after_request
def security_headers(resp):
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'",
    )
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


# ---------------- routes ----------------

def _require_valid_station(code):
    """Validate code against a trusted list; returns (stations, station) or aborts."""
    try:
        stations = get_passenger_stations(allow_stale=False)
    except requests.RequestException:
        logger.exception("Could not load station list")
        abort(502, description=GENERIC_ERROR)
    station = next((s for s in stations if s["stationShortCode"] == code), None)
    if station is None:
        abort(404, description=f"Unknown station: {code}")
    return stations, station


@app.route("/")
def index():
    try:
        stations = get_passenger_stations()
    except requests.RequestException:
        logger.exception("Could not load station list")
        return render_template("index.html", stations=[], error=GENERIC_ERROR), 502
    return render_template("index.html", stations=stations, error=None)


@app.route("/station", methods=["GET"])
def station_select():
    code = request.args.get("code", "").strip().upper()
    if not code:
        return redirect(url_for("index"))
    try:
        stations = get_passenger_stations(allow_stale=False)
    except requests.RequestException:
        logger.exception("Station validation failed for %s", code)
        return redirect(url_for("index"))
    if not any(s["stationShortCode"] == code for s in stations):
        abort(404, description=f"Unknown station: {code}")
    return redirect(url_for("departures", code=code))


@app.route("/station/<code>")
def departures(code):
    code = code.upper()
    stations, station = _require_valid_station(code)
    result = live_departures(code)
    return render_template(
        "departures.html",
        station_name=station["stationName"],
        station_code=code,
        rows=result["rows"],
        stations=stations,
        error=result["error"],
        refreshed=int(time.time()),
    )


@app.route("/station/<code>/partial")
def departures_partial(code):
    """HTML fragment (just the table body) fetched by the auto-refresh JS."""
    code = code.upper()
    _require_valid_station(code)
    result = live_departures(code)
    return render_template("_rows.html", rows=result["rows"], error=result["error"])


@app.route("/api/v1/station/<code>")
def api_departures(code):
    """Same data as JSON for scripts / other clients."""
    code = code.upper()
    _require_valid_station(code)
    result = live_departures(code)
    return jsonify({
        "station": code,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": result["error"],
        "departures": result["rows"],
    })


if __name__ == "__main__":
    app.run(debug=DEBUG)