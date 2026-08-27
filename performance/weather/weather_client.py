"""
Real-time weather integration for the Construction Performance component.

Fetches current weather for a project's exact site coordinates (preferred,
when the project has latitude/longitude on file) or its district name
(fallback, for projects created before coordinates existed), and maps it
onto the SAME four severity labels the existing trained model already
expects (pipeline/feature_engineer.py:WEATHER_MAP -> "No disruption" /
"Minor" / "Moderate" / "Severe"). No changes are made to WEATHER_MAP itself
or to the model's feature contract - this module only produces one of those
four existing strings from a live weather reading.

Provider: OpenWeatherMap "Current Weather Data" endpoint (plain REST/JSON,
no extra SDK needed - `requests` is already a project dependency).
Docs: https://openweathermap.org/current

Configuration (performance/.env):
    WEATHER_API_KEY        - required to make live calls. If unset or the
                              live call fails/times out, this module returns
                              a safe fallback instead of raising, so
                              /progress/predict never hard-fails just because
                              weather is unavailable.
    WEATHER_API_BASE_URL   - optional override, defaults to OpenWeatherMap.
    WEATHER_API_TIMEOUT_SECONDS - optional override, defaults to 5.
    WEATHER_API_COUNTRY_CODE    - optional override, defaults to "LK"
                              (Sri Lanka), appended to the district name
                              for the provider's city lookup.

Mapping thresholds below are a proposed default (flagged in the Phase 1
report as a product decision, not a purely technical one) based on
OpenWeatherMap's condition-code groups and reported rainfall volume.
Adjust SEVERITY_BY_CONDITION_GROUP / RAIN_MM_THRESHOLDS if different
thresholds are preferred - both are plain module-level constants.
"""

import os
import requests

from pipeline.feature_engineer import WEATHER_MAP

DEFAULT_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
FALLBACK_LABEL = "No disruption"

# OpenWeatherMap condition-code groups -> baseline severity label.
# https://openweathermap.org/weather-conditions
SEVERITY_BY_CONDITION_GROUP = {
    "thunderstorm": "Severe",      # 2xx
    "snow": "Severe",              # 6xx (not typical for Sri Lanka, handled for completeness)
    "drizzle": "Minor",            # 3xx
    "atmosphere": "Minor",         # 7xx - mist/fog/haze/dust
    "clear": "No disruption",      # 800
    "clouds_light": "No disruption",   # 801-802 few/scattered clouds
    "clouds_heavy": "Minor",       # 803-804 broken/overcast clouds
}

# Rain-group (5xx) condition IDs mapped individually since intensity varies widely.
RAIN_CONDITION_SEVERITY = {
    500: "Minor",       # light rain
    501: "Moderate",    # moderate rain
    502: "Severe",      # heavy rain
    503: "Severe",      # very heavy rain
    504: "Severe",      # extreme rain
    511: "Severe",      # freezing rain
    520: "Moderate",    # light shower rain
    521: "Moderate",    # shower rain
    522: "Severe",      # heavy shower rain
    531: "Severe",      # ragged shower rain
}

# Rainfall volume (mm, last 1h if provided by the API) can bump severity up
# a level even if the condition code alone would suggest less impact.
RAIN_MM_SEVERE = 20.0
RAIN_MM_MODERATE = 5.0
RAIN_MM_MINOR = 0.0

# Sustained high wind is treated as an independent severity escalation.
WIND_MPS_SEVERE = 15.0
WIND_MPS_MODERATE = 8.0

_SEVERITY_ORDER = ["No disruption", "Minor", "Moderate", "Severe"]


def _condition_group(condition_id: int) -> str:
    if 200 <= condition_id < 300:
        return "thunderstorm"
    if 300 <= condition_id < 400:
        return "drizzle"
    if 500 <= condition_id < 600:
        return "rain"
    if 600 <= condition_id < 700:
        return "snow"
    if 700 <= condition_id < 800:
        return "atmosphere"
    if condition_id == 800:
        return "clear"
    if condition_id in (801, 802):
        return "clouds_light"
    if condition_id in (803, 804):
        return "clouds_heavy"
    return "clear"


def _severity_from_condition(condition_id: int) -> str:
    group = _condition_group(condition_id)
    if group == "rain":
        return RAIN_CONDITION_SEVERITY.get(condition_id, "Moderate")
    return SEVERITY_BY_CONDITION_GROUP.get(group, "No disruption")


def _severity_from_rain_volume(rain_mm: float) -> str:
    if rain_mm >= RAIN_MM_SEVERE:
        return "Severe"
    if rain_mm >= RAIN_MM_MODERATE:
        return "Moderate"
    if rain_mm > RAIN_MM_MINOR:
        return "Minor"
    return "No disruption"


def _severity_from_wind(wind_mps: float) -> str:
    if wind_mps >= WIND_MPS_SEVERE:
        return "Severe"
    if wind_mps >= WIND_MPS_MODERATE:
        return "Moderate"
    return "No disruption"


def _max_severity(*labels: str) -> str:
    best = "No disruption"
    for label in labels:
        if label in _SEVERITY_ORDER and _SEVERITY_ORDER.index(label) > _SEVERITY_ORDER.index(best):
            best = label
    return best


def map_condition_to_severity(condition_id: int, rain_mm: float = 0.0, wind_mps: float = 0.0) -> str:
    """
    Pure function: OpenWeatherMap condition code + rainfall + wind -> one of
    the 4 existing WEATHER_MAP labels. No network call, unit-testable in
    isolation.
    """
    severity = _max_severity(
        _severity_from_condition(condition_id),
        _severity_from_rain_volume(rain_mm),
        _severity_from_wind(wind_mps),
    )
    if severity not in WEATHER_MAP:
        # Defensive guard: never return a label the model doesn't know about.
        return FALLBACK_LABEL
    return severity


def validate_coordinates(latitude, longitude) -> list:
    """
    Pure validation for an optional (latitude, longitude) pair, used by
    POST /schedule and PATCH /project/<id>/location. Coordinates are
    optional, but if given, both must be present (not just one) and must be
    numeric values within valid ranges. Returns a list of human-readable
    error strings (empty list = valid).
    """
    errors = []
    has_lat = latitude not in (None, "")
    has_lon = longitude not in (None, "")

    if has_lat != has_lon:
        errors.append("latitude and longitude must be provided together.")
        return errors
    if not has_lat and not has_lon:
        return errors

    try:
        lat_f = float(latitude)
        if lat_f < -90 or lat_f > 90:
            errors.append("latitude must be between -90 and 90.")
    except (TypeError, ValueError):
        errors.append("latitude must be numeric.")

    try:
        lon_f = float(longitude)
        if lon_f < -180 or lon_f > 180:
            errors.append("longitude must be between -180 and 180.")
    except (TypeError, ValueError):
        errors.append("longitude must be numeric.")

    return errors


def _safe_error_message(exc: Exception) -> str:
    """
    Converts a weather-lookup exception into a message that is safe to put
    in an API response or a log line - i.e. one that can NEVER contain the
    OpenWeatherMap API key or the full request URL/query string.

    requests' own exception __str__ (HTTPError, RequestException, etc.)
    embeds the PreparedRequest URL, which includes `appid=<key>` as a query
    param - str(exc) must never be surfaced for those. The two exception
    types raised directly by this module (RuntimeError/ValueError, both
    below) carry only hardcoded, key-free messages, so those alone are safe
    to pass through as-is.
    """
    if isinstance(exc, (RuntimeError, ValueError)):
        return str(exc)
    if isinstance(exc, requests.exceptions.Timeout):
        return "Weather provider request timed out."
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else "unknown"
        return f"Weather provider returned HTTP {status}."
    if isinstance(exc, requests.exceptions.RequestException):
        return "Weather provider request failed due to a network error."
    return "Weather lookup failed unexpectedly."


def _fetch_raw_weather(district: str = None, latitude: float = None, longitude: float = None) -> dict:
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        raise RuntimeError("WEATHER_API_KEY is not configured.")

    base_url = os.getenv("WEATHER_API_BASE_URL", DEFAULT_BASE_URL)
    timeout = float(os.getenv("WEATHER_API_TIMEOUT_SECONDS", "5"))

    if latitude is not None and longitude is not None:
        params = {"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"}
    elif district:
        country_code = os.getenv("WEATHER_API_COUNTRY_CODE", "LK")
        params = {"q": f"{district},{country_code}", "appid": api_key, "units": "metric"}
    else:
        raise ValueError("Either district or latitude/longitude must be provided.")

    response = requests.get(base_url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_current_weather(district: str = None, latitude: float = None, longitude: float = None) -> dict:
    """
    Fetch live weather and map it onto the existing 4-label severity scale.
    Prefers exact site coordinates (lat/lon) when both are given - this is
    the precise, per-project-site lookup. Falls back to a district-name
    lookup when coordinates are absent, so projects created before
    coordinates existed keep working unchanged.

    Never raises - on any failure (missing API key, network error, timeout,
    malformed response) this returns a fallback result with
    "source": "fallback" and a redacted "error" field (see
    _safe_error_message - never contains the API key or request URL), so
    callers (the weather preview endpoint and /progress/predict) can decide
    how to proceed without the whole request failing.
    """
    used_coordinates = latitude is not None and longitude is not None
    location_source = "coordinates" if used_coordinates else "district"
    try:
        raw = _fetch_raw_weather(district=district, latitude=latitude, longitude=longitude)

        weather_list = raw.get("weather") or [{}]
        condition_id = int(weather_list[0].get("id", 800))
        condition_desc = weather_list[0].get("description", "unknown")

        main = raw.get("main", {})
        temperature_c = main.get("temp")

        rain = raw.get("rain", {}) or {}
        rain_mm = float(rain.get("1h", rain.get("3h", 0.0)) or 0.0)

        wind = raw.get("wind", {}) or {}
        wind_mps = float(wind.get("speed", 0.0) or 0.0)

        severity = map_condition_to_severity(condition_id, rain_mm=rain_mm, wind_mps=wind_mps)

        return {
            "success": True,
            "source": "live",
            "location_source": location_source,
            "district": district,
            "latitude": latitude,
            "longitude": longitude,
            "temperature_c": temperature_c,
            "condition": condition_desc,
            "rainfall_mm": rain_mm,
            "wind_mps": wind_mps,
            "weather_severity": severity,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "source": "fallback",
            "location_source": location_source,
            "district": district,
            "latitude": latitude,
            "longitude": longitude,
            "temperature_c": None,
            "condition": None,
            "rainfall_mm": None,
            "wind_mps": None,
            "weather_severity": FALLBACK_LABEL,
            "error": _safe_error_message(exc),
        }


def resolve_weather_severity(
    district: str = None,
    latitude: float = None,
    longitude: float = None,
    manual_override: str = None,
) -> dict:
    """
    Used by /progress/predict. If the caller explicitly supplied a valid
    manual weather_severity (kept as an optional fallback field per the
    Phase 1 plan), it takes precedence and no live call is made. Otherwise
    fetches live weather - preferring the project's exact coordinates when
    available, falling back to district lookup otherwise; if that also
    fails, falls back to the safe default label.
    """
    if manual_override and manual_override in WEATHER_MAP:
        return {
            "success": True,
            "source": "manual_override",
            "location_source": "manual_override",
            "district": district,
            "latitude": latitude,
            "longitude": longitude,
            "temperature_c": None,
            "condition": None,
            "rainfall_mm": None,
            "wind_mps": None,
            "weather_severity": manual_override,
            "error": None,
        }
    return get_current_weather(district=district, latitude=latitude, longitude=longitude)
