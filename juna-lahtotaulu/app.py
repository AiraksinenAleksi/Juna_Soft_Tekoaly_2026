from flask import Flask, render_template, jsonify, request
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_URL = "https://rata.digitraffic.fi"
FINLAND_TZ = ZoneInfo("Europe/Helsinki")
TIMEOUT = 10

ALLOWED_STATIONS = {
    "HKI": "Helsinki",
    "TPE": "Tampere",
    "KOK": "Kokkola"
}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "JunaLahtotaulu/1.0"
}


def parse_time(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(FINLAND_TZ)
    except (ValueError, TypeError):
        return None


def format_time(value):
    return value.strftime("%H:%M") if value else None


def get_stations():
    response = requests.get(
        f"{BASE_URL}/api/v1/metadata/stations",
        headers=HEADERS,
        timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def get_destination(train):
    rows = train.get("timeTableRows", [])

    arrivals = [
        row for row in rows
        if row.get("type") == "ARRIVAL"
        and row.get("stationShortCode")
    ]

    if not arrivals:
        return None

    return arrivals[-1]["stationShortCode"]


def get_departures(station_code):
    if station_code not in ALLOWED_STATIONS:
        raise ValueError("Invalid station")

    url = (
        f"{BASE_URL}/api/v1/live-trains/station/{station_code}"
        "?arrived_trains=0"
        "&arriving_trains=0"
        "&departed_trains=0"
        "&departing_trains=10"
        "&include_nonstopping=false"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )
    response.raise_for_status()

    trains = response.json()
    departures = []

    for train in trains:
        rows = train.get("timeTableRows", [])

        departure = next(
            (
                row for row in rows
                if row.get("stationShortCode") == station_code
                and row.get("type") == "DEPARTURE"
            ),
            None
        )

        if not departure:
            continue

        scheduled = parse_time(departure.get("scheduledTime"))
        actual = parse_time(departure.get("actualTime"))
        estimate = parse_time(departure.get("liveEstimateTime"))

        if not scheduled:
            continue

        current = actual or estimate

        delay = None
        if current:
            delay = round(
                (current - scheduled).total_seconds() / 60
            )

        departures.append({
            "train_number": train.get("trainNumber"),
            "destination": get_destination(train),
            "scheduled_time": format_time(scheduled),
            "estimated_time": format_time(current),
            "time_status": (
                "Toteutunut" if actual
                else "Arvio" if estimate
                else "Ei arviota"
            ),
            "delay_minutes": delay
        })

    departures.sort(
        key=lambda item: item["scheduled_time"]
    )

    return departures


@app.route("/")
def index():
    return render_template(
        "index.html",
        stations=ALLOWED_STATIONS
    )


@app.route("/api/stations")
def api_stations():
    try:
        metadata = get_stations()

        result = [
            {
                "code": station.get("stationShortCode"),
                "name": station.get("stationName")
            }
            for station in metadata
            if station.get("stationShortCode")
        ]

        return jsonify(result)

    except requests.RequestException:
        return jsonify({
            "error": "Asematietoja ei saatavilla."
        }), 503


@app.route("/api/departures")
def api_departures():
    station = request.args.get(
        "station", "HKI"
    ).upper()

    if station not in ALLOWED_STATIONS:
        return jsonify({
            "error": "Valittu asema ei ole sallittu."
        }), 400

    try:
        departures = get_departures(station)

        return jsonify({
            "station": ALLOWED_STATIONS[station],
            "station_code": station,
            "departures": departures
        })

    except requests.Timeout:
        return jsonify({
            "error": "Junatietojen haku aikakatkaistiin."
        }), 504

    except requests.RequestException:
        return jsonify({
            "error": "Junatietoja ei voitu hakea."
        }), 503

    except (ValueError, TypeError, KeyError):
        return jsonify({
            "error": "Junatietojen käsittely epäonnistui."
        }), 502


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
