"""
Regression tests for the November 2026 correctness pass.

Each test pins a bug that reached the user, so it cannot silently return:

- the conformal datum-offset bug (q_hat absorbed a +5.35 m level offset,
  which zeroed the extraction quota at most locations),
- the PDF report heatmap / provenance section toggles,
- the admin UI-settings round trip that controls the provenance
  option's visibility in the PDF generator pop-up,
- the Earth Engine raster disk cache (keying + round trip),
- per-variable provenance stamping on the providers.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.app import app, state


def test_conformal_calibration_is_bias_corrected():
    """q_hat must measure residual SPREAD around the observed datum,
    not the datum offset itself (the offset lives in forecast_bias_m)."""
    assert state.pipeline.forecast_bias_m > 1.0
    assert 0.5 < state.conformal.q_hat < 6.0


def test_analytic_quota_positive_at_centre_and_corner():
    """The exact user report: quota was 0 at every location. After the
    bias correction it must be positive across the grid, including a
    low-head corner cell."""
    forecast = state.pipeline.analytic_forecast(40.5, -88.5, horizon=12)
    assert forecast["recommended_quota"] > 0
    corner = state.pipeline.analytic_forecast(39.6, -89.4, horizon=12)
    assert corner["recommended_quota"] > 0


def test_gee_cache_key_and_roundtrip(tmp_path, monkeypatch):
    import src.ingestion.realtime_provider as rp

    monkeypatch.setattr(rp, "_GEE_CACHE_DIR", tmp_path)
    windows = [("2023-01-01", "2023-02-01"), ("2023-02-01", "2023-03-01")]
    key_a = rp._gee_cache_key("ganges", [77.0, 25.0, 81.0, 28.0], 36, windows)
    key_b = rp._gee_cache_key("illinois", [-89.5, 39.5, -87.5, 41.5], 36, windows)
    assert key_a != key_b  # region/bounds are part of the key

    rasters = {"P": np.ones((2, 16, 16)), "ET": np.zeros((2, 16, 16))}
    sources = {"P": "live", "ET": "fallback"}
    assert rp._gee_cache_load(key_a) is None
    rp._gee_cache_save(key_a, rasters, sources, windows)
    loaded = rp._gee_cache_load(key_a)
    assert loaded is not None
    loaded_rasters, info = loaded
    assert np.array_equal(loaded_rasters["P"], rasters["P"])
    assert info["sources"] == sources


def test_synthetic_provider_stamps_provenance():
    from src.ingestion.synthetic_provider import SyntheticDataProvider

    provider = SyntheticDataProvider()
    rasters = provider.fetch_hydroclimate_rasters(timesteps=4)
    assert set(provider.variable_sources) == set(rasters)
    assert all(v == "synthetic" for v in provider.variable_sources.values())


def test_status_exposes_ui_settings_and_sources():
    client = TestClient(app)
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    body = res.json()
    assert "show_provenance_option" in body["ui_settings"]
    sources = body["provider_metadata"].get("variable_sources") or {}
    assert sources.get("P") == "synthetic"  # default boot mode


def test_admin_ui_settings_roundtrip():
    client = TestClient(app)
    original = client.get("/api/v1/admin/ui-settings").json()["ui_settings"]
    try:
        res = client.post(
            "/api/v1/admin/ui-settings",
            json={"show_provenance_option": False},
        )
        assert res.status_code == 200
        assert res.json()["ui_settings"]["show_provenance_option"] is False
        status = client.get("/api/v1/status").json()
        assert status["ui_settings"]["show_provenance_option"] is False
    finally:
        client.post(
            "/api/v1/admin/ui-settings",
            json={"show_provenance_option": original["show_provenance_option"]},
        )


def test_report_heatmap_and_provenance_toggles():
    client = TestClient(app)

    res = client.get("/api/v1/reports/view?lat=40.5&lon=-88.5")
    assert res.status_code == 200
    assert res.text.count("<rect") == 256  # heatmap on by default
    assert "Data Provenance" in res.text
    assert "Synthetic benchmark data" in res.text

    res_off = client.get(
        "/api/v1/reports/view?lat=40.5&lon=-88.5&sec_heatmap=0&sec_provenance=0"
    )
    assert res_off.status_code == 200
    assert res_off.text.count("<rect") == 0
    assert "Data Provenance" not in res_off.text


# ---------------------------------------------------------------------------
# ThingSpeak field-sensor integration (November 2026). Tests never touch
# the real network: the fetch helper is monkeypatched or the key removed.
# ---------------------------------------------------------------------------

_CANNED_TS = {
    "configured": True,
    "channel": {"id": 3575415, "name": "IGMS", "description": "borewell rig"},
    "labels": {
        "temperature": "Temperature",
        "humidity": "Humidity",
        "soil_moisture": "Soil Moisture",
        "water_level": "Water Level",
        "discharge_flow": "Discharge Flow",
    },
    "latest": {
        "timestamp": "2026-11-12T06:40:35Z",
        "entry_id": 114,
        "temperature": 31.9,
        "humidity": 28.6,
        "soil_moisture": 5.0,
        "water_level": 7.46,
        "discharge_flow": 0.0,
    },
    "series": {"water_level": [["2026-11-12T06:40:20Z", 7.46], ["2026-11-12T06:40:35Z", 7.44]]},
    "error": None,
}


def test_thingspeak_unconfigured_is_graceful(monkeypatch):
    import importlib

    app_module = importlib.import_module("src.api.app")

    monkeypatch.delenv("THINGSPEAK_READ_KEY", raising=False)
    app_module._ts_cache.update({"fetched_at": 0.0, "payload": None, "results": None})
    client = TestClient(app)
    res = client.get("/api/v1/sensors/thingspeak")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is False
    assert body["latest"] is None


def test_thingspeak_endpoint_serves_normalized_feed(monkeypatch):
    import importlib

    app_module = importlib.import_module("src.api.app")

    monkeypatch.setattr(app_module, "_fetch_thingspeak", lambda results=100: _CANNED_TS)
    client = TestClient(app)
    res = client.get("/api/v1/sensors/thingspeak")
    assert res.status_code == 200
    body = res.json()
    assert body["channel"]["name"] == "IGMS"
    assert body["latest"]["water_level"] == 7.46


def test_report_sensor_block_toggle(monkeypatch):
    import importlib

    app_module = importlib.import_module("src.api.app")

    monkeypatch.setattr(app_module, "_fetch_thingspeak", lambda results=100: _CANNED_TS)
    client = TestClient(app)

    res = client.get("/api/v1/reports/view?lat=40.5&lon=-88.5")
    assert res.status_code == 200
    assert "Field Sensor Readings" in res.text
    assert "7.46" in res.text

    res_off = client.get("/api/v1/reports/view?lat=40.5&lon=-88.5&sec_sensors=0")
    assert res_off.status_code == 200
    assert "Field Sensor Readings" not in res_off.text


def test_admin_sensors_visibility_and_report_enforcement(monkeypatch):
    """The admin IoT-sensors switch: partial updates must not clobber
    the provenance flag, /status must expose it, and the report must
    exclude sensor readings while it is off — even when the request
    explicitly asks for them (stale client)."""
    import importlib

    app_module = importlib.import_module("src.api.app")
    monkeypatch.setattr(app_module, "_fetch_thingspeak", lambda results=100: _CANNED_TS)
    client = TestClient(app)
    try:
        res = client.post("/api/v1/admin/ui-settings", json={"show_sensors": False})
        assert res.status_code == 200
        settings = res.json()["ui_settings"]
        assert settings["show_sensors"] is False
        assert "show_provenance_option" in settings  # not clobbered

        status = client.get("/api/v1/status").json()
        assert status["ui_settings"]["show_sensors"] is False

        rep = client.get("/api/v1/reports/view?lat=40.5&lon=-88.5&sec_sensors=1")
        assert rep.status_code == 200
        assert "Field Sensor Readings" not in rep.text
    finally:
        client.post("/api/v1/admin/ui-settings", json={"show_sensors": True})

    rep = client.get("/api/v1/reports/view?lat=40.5&lon=-88.5&sec_sensors=1")
    assert "Field Sensor Readings" in rep.text
