import math
import re

EARTH_RADIUS_M = 6_371_000.0
WEB_MERCATOR_HALF_WORLD = 20_037_508.342789244


def wgs84_to_web_mercator(latitude: float, longitude: float) -> tuple[float, float]:
    """Convert WGS84 to the EPSG:3857 coordinates used by GovMap's deals API."""
    latitude = max(min(latitude, 85.05112878), -85.05112878)
    x = longitude * WEB_MERCATOR_HALF_WORLD / 180.0
    y = math.log(math.tan((90.0 + latitude) * math.pi / 360.0)) / (math.pi / 180.0)
    y *= WEB_MERCATOR_HALF_WORLD / 180.0
    return x, y


def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    longitude = x / WEB_MERCATOR_HALF_WORLD * 180.0
    latitude = y / WEB_MERCATOR_HALF_WORLD * 180.0
    latitude = (
        180.0
        / math.pi
        * (2.0 * math.atan(math.exp(latitude * math.pi / 180.0)) - math.pi / 2.0)
    )
    return latitude, longitude


def wkt_center_wgs84(wkt: str | None) -> tuple[float, float] | None:
    if not wkt:
        return None
    coordinates = [
        (float(x), float(y))
        for x, y in re.findall(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", wkt)
    ]
    if not coordinates:
        return None
    x = (
        min(point[0] for point in coordinates) + max(point[0] for point in coordinates)
    ) / 2.0
    y = (
        min(point[1] for point in coordinates) + max(point[1] for point in coordinates)
    ) / 2.0
    return web_mercator_to_wgs84(x, y)


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
