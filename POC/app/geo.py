from shapely.geometry import shape, mapping, Polygon, Point
from shapely.ops import transform, unary_union
from pyproj import Transformer

TO_ITM = Transformer.from_crs(4326, 2039, always_xy=True).transform
TO_WGS = Transformer.from_crs(2039, 4326, always_xy=True).transform

def itm(geo):
    return transform(TO_ITM, shape(geo) if isinstance(geo, dict) else geo)

def wgs(geom):
    return mapping(transform(TO_WGS, geom))

def validate_polygon(geo, boundary, max_area):
    p = shape(geo)
    if p.geom_type != 'Polygon' or p.is_empty or not p.is_valid or len(p.exterior.coords)>500:
        raise ValueError('הפוליגון אינו תקין; יש לצייר אזור ללא חצייה עצמית')
    p = itm(p)
    if p.area <= 0 or p.area > max_area:
        raise ValueError(f'מגבלת הפיילוט היא {max_area / 1000:g} דונם')
    if not boundary.covers(p):
        raise ValueError('כל אזור החיפוש חייב להיות בתוך גבול הרצליה הרשמי')
    return p

def circle_polygon(center, radius_m, boundary, max_radius_m, max_area):
    """Build the authoritative search geometry in ITM metres."""
    if not isinstance(center, dict) or set(center) != {'lat','lon'}:
        raise ValueError('יש לבחור נקודת מרכז תקינה')
    lat=float(center['lat']);lon=float(center['lon']);radius=float(radius_m)
    if not (32.0 <= lat <= 32.4 and 34.7 <= lon <= 35.0):
        raise ValueError('נקודת המרכז אינה באזור הרצליה')
    if radius <= 0 or radius > max_radius_m:
        raise ValueError(f'רדיוס הפיילוט המרבי הוא {max_radius_m:g} מטר')
    point=transform(TO_ITM,Point(lon,lat))
    polygon=point.buffer(radius,quad_segs=32)
    if polygon.area > max_area:
        raise ValueError(f'מגבלת הפיילוט היא {max_area / 1000:g} דונם')
    if not boundary.covers(polygon):
        raise ValueError('כל מעגל החיפוש חייב להיות בתוך גבול הרצליה הרשמי')
    return polygon

def center_selected(building, polygon):
    # Centroid in metres; boundary points are included, consistently with covers.
    return polygon.covers(building.centroid)

def match_parcels(building, parcels):
    matches = []
    for parcel in parcels:
        geom = shape(parcel['geometry'])
        overlap = building.intersection(geom).area / building.area if building.area else 0
        if overlap > 0.02:
            matches.append((overlap, parcel))
    matches.sort(key=lambda item: (-item[0], str(item[1]['id'])))
    return matches

def pair_geometry(a, b, public_separation_verified):
    if not public_separation_verified:
        return None
    if a.intersection(b).area > .01 or a.boundary.intersection(b.boundary).length < .1:
        return None
    return unary_union([a,b])
