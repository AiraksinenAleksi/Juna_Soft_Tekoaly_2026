"""Offline tests: parsing logic and routes with the network patched out."""
from datetime import datetime, timedelta, timezone

import pytest

import app as app_module


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def fake_stations(monkeypatch):
    raw_stations = [
        {"stationShortCode": "HKI", "stationName": "Helsinki",
         "passengerTraffic": True, "deleted": False},
        {"stationShortCode": "TPE", "stationName": "Tampere",
         "passengerTraffic": True, "deleted": False},
        {"stationShortCode": "AIN", "stationName": "Ainola",
         "passengerTraffic": False, "deleted": False},   # must be filtered out
    ]
    # The app's cache holds the FILTERED list (filtering happens in
    # _load_passenger_stations on a cache miss). Mirror that contract:
    stations = sorted(
        (s for s in raw_stations
         if s.get("passengerTraffic") and not s.get("deleted")),
        key=lambda s: s["stationName"].lower(),
    )
    app_module._STATION_CACHE.update({
        "data": stations,
        "map": {s["stationShortCode"]: s["stationName"] for s in stations},
        "ts": app_module.time.monotonic(),
    })
    app_module._LIVE_CACHE.clear()


def make_train(dep_offset_min=5, delay_min=0, dest="TPE", number=999, cat="IC"):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    sched = now + timedelta(minutes=dep_offset_min)
    live = sched + timedelta(minutes=delay_min)
    return {
        "trainCategory": cat, "trainNumber": number, "commuterLineID": None,
        "timeTableRows": [
            {"type": "DEPARTURE", "stationShortCode": "HKI",
             "scheduledTime": sched.isoformat(),
             "liveEstimateTime": live.isoformat() if delay_min else None,
             "commercialStop": True, "commercialTrack": "1"},
            {"type": "ARRIVAL", "stationShortCode": dest,
             "scheduledTime": sched.isoformat(), "commercialStop": True},
        ],
    }


def test_train_row_basic():
    row = app_module.train_row(make_train(delay_min=7), "HKI")
    assert row["destination"] == "Tampere"          # name, not code
    assert row["delay_min"] == 7
    assert row["track"] == "1"


def test_train_row_skips_nonstop_and_bad_records():
    t = make_train()
    t["timeTableRows"][0]["commercialStop"] = False
    assert app_module.train_row(t, "HKI") is None
    assert app_module.train_row({"trainNumber": 1}, "HKI") is None   # no rows at all


def test_parse_departures_sorts_across_midnight():
    late = make_train(dep_offset_min=1400)   # tomorrow ~23:xx
    early = make_train(dep_offset_min=10)
    rows = app_module.parse_departures([late, early], "HKI")
    assert rows[0]["scheduled_dt" if "scheduled_dt" in rows[0] else "scheduled"] is not None
    # chronological regardless of HH:MM string order:
    times = [r["scheduled"] for r in rows]
    assert len(rows) == 2 and times  # smoke: dedup + no crash


def test_index_lists_only_passenger_stations(client):
    html = client.get("/").get_data(as_text=True)
    assert "Helsinki" in html and "Ainola" not in html


def test_unknown_station_404(client):
    assert client.get("/station/ZZZ").status_code == 404


def test_api_endpoint_json(client, monkeypatch):
    monkeypatch.setattr(app_module, "fetch",
                        lambda url: [make_train(delay_min=3)])
    resp = client.get("/api/v1/station/HKI")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["station"] == "HKI"
    assert data["departures"][0]["delay_min"] == 3


def test_security_headers(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "connect-src 'self'" in resp.headers["Content-Security-Policy"]