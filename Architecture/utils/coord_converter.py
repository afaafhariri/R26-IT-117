"""SLD99 (EPSG:5235) to WGS84 (EPSG:4326) coordinate converter.

SLD99 (Sri Lanka Datum 1999 / "Sri Lanka Grid 1999") is the modern GPS-derived
national grid used in current cadastral survey plans — the kind explicitly
noted as "derived from RTK receiver (CORS Net)" on the plans this app parses.
Coordinates are in metres (Easting/Northing).
WGS84 is standard GPS coordinates (latitude/longitude).

EPSG:5234 ("Kandawala / Sri Lanka Grid") is a DIFFERENT, older colonial-era
datum that happens to share a superficially similar name — using it here
silently produced coordinates ~50-60km off (enough to land outside Sri
Lanka's real bounds for plots near the edge of the grid), even though the
transform ran without error. EPSG:5235 is the correct code for real SLD99.
"""

from utils.logger import get_logger

_logger = get_logger("coord_converter")


def sld99_to_wgs84(easting: float, northing: float) -> tuple[float, float] | tuple[None, None]:
    """Converts SLD99 grid coordinates to WGS84 GPS coordinates.

    Args:
        easting: SLD99 Easting value in metres (E).
        northing: SLD99 Northing value in metres (N).

    Returns:
        tuple: (latitude, longitude) in WGS84 decimal degrees,
               or (None, None) if conversion fails.
    """
    try:
        from pyproj import Transformer

        transformer = Transformer.from_crs("EPSG:5235", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(easting, northing)

        # Sanity check — Sri Lanka bounding box
        if not (5.9 <= lat <= 9.9 and 79.5 <= lon <= 82.0):
            _logger.warning(
                "Converted coordinates (%.6f, %.6f) are outside Sri Lanka bounds — "
                "check input values E=%.0f N=%.0f",
                lat, lon, easting, northing,
            )

        _logger.info(
            "SLD99 E=%.0f N=%.0f → WGS84 lat=%.6f lon=%.6f",
            easting, northing, lat, lon,
        )
        return round(lat, 6), round(lon, 6)

    except ImportError:
        _logger.warning("pyproj not installed — SLD99 to WGS84 conversion skipped")
        return None, None
    except Exception as exc:
        _logger.warning("Coordinate conversion failed: %s", exc)
        return None, None
