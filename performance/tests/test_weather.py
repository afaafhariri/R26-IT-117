import pytest
import requests

from weather.weather_client import (
    get_current_weather,
    map_condition_to_severity,
    resolve_weather_severity,
    validate_coordinates,
)


def test_clear_sky_is_no_disruption():
    assert map_condition_to_severity(condition_id=800, rain_mm=0.0, wind_mps=2.0) == "No disruption"


def test_light_rain_is_minor():
    assert map_condition_to_severity(condition_id=500, rain_mm=1.0, wind_mps=2.0) == "Minor"


def test_moderate_rain_is_moderate():
    assert map_condition_to_severity(condition_id=501, rain_mm=6.0, wind_mps=3.0) == "Moderate"


def test_heavy_rain_is_severe():
    assert map_condition_to_severity(condition_id=502, rain_mm=25.0, wind_mps=5.0) == "Severe"


def test_thunderstorm_is_severe_regardless_of_rain_volume():
    assert map_condition_to_severity(condition_id=200, rain_mm=0.5, wind_mps=1.0) == "Severe"


def test_high_wind_alone_escalates_to_severe():
    assert map_condition_to_severity(condition_id=800, rain_mm=0.0, wind_mps=16.0) == "Severe"


def test_unknown_condition_id_falls_back_to_no_disruption():
    assert map_condition_to_severity(condition_id=999, rain_mm=0.0, wind_mps=0.0) == "No disruption"


def test_manual_override_short_circuits_live_call():
    result = resolve_weather_severity(district="Colombo", manual_override="Severe")
    assert result["weather_severity"] == "Severe"
    assert result["source"] == "manual_override"


def test_invalid_manual_override_falls_through_to_live_fetch(monkeypatch):
    # "Bad" is not one of the 4 valid WEATHER_MAP labels, so this should NOT
    # short-circuit - it should attempt a live fetch instead. With no
    # WEATHER_API_KEY configured, that live fetch itself fails gracefully
    # and returns the safe fallback label.
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    result = resolve_weather_severity(district="Colombo", manual_override="Bad")
    assert result["weather_severity"] == "No disruption"
    assert result["source"] == "fallback"


def test_missing_api_key_returns_graceful_fallback_not_an_exception(monkeypatch):
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)

    result = get_current_weather(district="Colombo")
    assert result["success"] is False
    assert result["source"] == "fallback"
    assert result["weather_severity"] == "No disruption"
    assert result["error"] is not None


# ---- Coordinate validation ----


def test_validate_coordinates_both_absent_is_valid():
    assert validate_coordinates(None, None) == []


def test_validate_coordinates_both_present_in_range_is_valid():
    assert validate_coordinates(6.9271, 79.8612) == []


def test_validate_coordinates_only_latitude_given_is_invalid():
    errors = validate_coordinates(6.9271, None)
    assert any("together" in e for e in errors)


def test_validate_coordinates_only_longitude_given_is_invalid():
    errors = validate_coordinates(None, 79.8612)
    assert any("together" in e for e in errors)


def test_validate_coordinates_out_of_range_latitude_is_invalid():
    errors = validate_coordinates(120.0, 79.8612)
    assert any("latitude" in e for e in errors)


def test_validate_coordinates_out_of_range_longitude_is_invalid():
    errors = validate_coordinates(6.9271, 200.0)
    assert any("longitude" in e for e in errors)


def test_validate_coordinates_non_numeric_is_invalid():
    errors = validate_coordinates("not-a-number", 79.8612)
    assert any("numeric" in e for e in errors)


# ---- Coordinate-based lookup vs. district fallback ----


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json_data


_SAMPLE_OWM_RESPONSE = {
    "weather": [{"id": 800, "description": "clear sky"}],
    "main": {"temp": 29.5},
    "rain": {},
    "wind": {"speed": 3.0},
}


def test_coordinates_preferred_over_district_when_both_available(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key-not-real")
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return _FakeResponse(_SAMPLE_OWM_RESPONSE)

    monkeypatch.setattr(requests, "get", fake_get)

    result = get_current_weather(district="Colombo", latitude=6.9271, longitude=79.8612)

    assert result["success"] is True
    assert result["source"] == "live"
    assert result["location_source"] == "coordinates"
    assert "lat" in captured["params"] and "lon" in captured["params"]
    assert "q" not in captured["params"]
    assert captured["params"]["lat"] == 6.9271
    assert captured["params"]["lon"] == 79.8612


def test_district_used_when_coordinates_absent(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key-not-real")
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return _FakeResponse(_SAMPLE_OWM_RESPONSE)

    monkeypatch.setattr(requests, "get", fake_get)

    result = get_current_weather(district="Colombo")

    assert result["success"] is True
    assert result["location_source"] == "district"
    assert "q" in captured["params"]
    assert captured["params"]["q"] == "Colombo,LK"


def test_resolve_weather_severity_passes_coordinates_through(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key-not-real")
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return _FakeResponse(_SAMPLE_OWM_RESPONSE)

    monkeypatch.setattr(requests, "get", fake_get)

    result = resolve_weather_severity(district="Colombo", latitude=6.9271, longitude=79.8612)

    assert result["source"] == "live"
    assert "lat" in captured["params"]


# ---- API key / URL must never leak into error messages ----


def test_http_error_message_never_contains_api_key(monkeypatch):
    secret_key = "super-secret-key-should-never-appear"
    monkeypatch.setenv("WEATHER_API_KEY", secret_key)

    def fake_get(url, params, timeout):
        return _FakeResponse({"cod": 401, "message": "Invalid API key"}, status_code=401)

    monkeypatch.setattr(requests, "get", fake_get)

    result = get_current_weather(district="Colombo")

    assert result["success"] is False
    assert result["error"] is not None
    assert secret_key not in result["error"]
    assert "appid" not in result["error"]
    assert "api.openweathermap.org" not in result["error"]


def test_timeout_error_message_never_contains_api_key(monkeypatch):
    secret_key = "super-secret-key-should-never-appear"
    monkeypatch.setenv("WEATHER_API_KEY", secret_key)

    def fake_get(url, params, timeout):
        raise requests.exceptions.Timeout(
            f"Connection to {url}?appid={secret_key} timed out"
        )

    monkeypatch.setattr(requests, "get", fake_get)

    result = get_current_weather(district="Colombo")

    assert result["success"] is False
    assert secret_key not in result["error"]
    assert "appid" not in result["error"]


def test_generic_request_exception_never_contains_api_key(monkeypatch):
    secret_key = "super-secret-key-should-never-appear"
    monkeypatch.setenv("WEATHER_API_KEY", secret_key)

    def fake_get(url, params, timeout):
        raise requests.exceptions.ConnectionError(
            f"Failed to connect to {url}?appid={secret_key}&units=metric"
        )

    monkeypatch.setattr(requests, "get", fake_get)

    result = get_current_weather(district="Colombo")

    assert result["success"] is False
    assert secret_key not in result["error"]
    assert "appid" not in result["error"]
