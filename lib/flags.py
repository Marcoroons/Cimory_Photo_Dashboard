"""Quality flag computation: GPS distance and per-day counts.

No AI here. GPS far is a plain Haversine distance against a per-MCM reference
point, or a supplied distance column. The daily count is a straight count of
submissions for that MCM on that date.
"""

from math import radians, sin, cos, asin, sqrt

DEFAULT_DAILY_LIMIT = 2
DEFAULT_GPS_THRESHOLD_KM = 5.0


def haversine(lat1, lon1, lat2, lon2) -> float:
    """Great circle distance between two points in kilometres."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6371.0


def gps_distance_km(lat, lon, gps_distance, ref_coord, threshold_km):
    """Return (distance_km_or_None, gps_far_bool_or_None).

    Uses the supplied gps_distance if present, else Haversine against the
    per-MCM reference coordinate, else leaves both unset because we simply do
    not know.
    """
    if gps_distance is not None:
        try:
            d = float(gps_distance)
            return d, d > threshold_km
        except (TypeError, ValueError):
            pass
    if lat is not None and lon is not None and ref_coord:
        try:
            d = haversine(float(lat), float(lon), float(ref_coord[0]), float(ref_coord[1]))
            return d, d > threshold_km
        except (TypeError, ValueError, IndexError):
            pass
    return None, None
