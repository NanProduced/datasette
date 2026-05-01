from datasette import hookimpl
from datasette.utils.asgi import Response, BadRequest
from datasette.utils import escape_sqlite
from datasette.filters import FilterArguments
import json


LATITUDE_COLUMNS = {"latitude", "lat", "y"}
LONGITUDE_COLUMNS = {"longitude", "lon", "lng", "x"}


def find_spatial_columns(columns):
    lat_col = None
    lon_col = None
    for col in columns:
        col_lower = col.lower()
        if col_lower in LATITUDE_COLUMNS and lat_col is None:
            lat_col = col
        if col_lower in LONGITUDE_COLUMNS and lon_col is None:
            lon_col = col
    return lat_col, lon_col


def parse_bbox(bbox_str):
    try:
        parts = [float(p.strip()) for p in bbox_str.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have 4 values")
        min_lon, min_lat, max_lon, max_lat = parts
        if min_lon > max_lon or min_lat > max_lat:
            raise ValueError("Invalid bbox coordinates")
        return min_lon, min_lat, max_lon, max_lat
    except (ValueError, AttributeError):
        raise BadRequest("Invalid _bbox parameter. Expected format: minLon,minLat,maxLon,maxLat")


def point_in_bbox(lon, lat, bbox):
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    try:
        lon = float(lon)
        lat = float(lat)
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
    except (TypeError, ValueError):
        return False


@hookimpl(specname="filters_from_request")
def bbox_filter(request, database, table, datasette):
    async def inner():
        if request.url_vars.get("format") != "geojson":
            return None
        
        if "_bbox" not in request.args:
            return None
        
        try:
            bbox = parse_bbox(request.args["_bbox"])
        except BadRequest:
            return None
        
        db = datasette.get_database(database)
        table_columns = await db.table_columns(table)
        
        lat_col, lon_col = find_spatial_columns(table_columns)
        if lat_col is None or lon_col is None:
            return None
        
        min_lon, min_lat, max_lon, max_lat = bbox
        
        where_clauses = [
            f"{escape_sqlite(lon_col)} >= :bbox_min_lon",
            f"{escape_sqlite(lon_col)} <= :bbox_max_lon",
            f"{escape_sqlite(lat_col)} >= :bbox_min_lat",
            f"{escape_sqlite(lat_col)} <= :bbox_max_lat",
        ]
        
        params = {
            "bbox_min_lon": min_lon,
            "bbox_max_lon": max_lon,
            "bbox_min_lat": min_lat,
            "bbox_max_lat": max_lat,
        }
        
        human_descriptions = [
            f"bounding box: {min_lon},{min_lat},{max_lon},{max_lat}"
        ]
        
        return FilterArguments(
            where_clauses=where_clauses,
            params=params,
            human_descriptions=human_descriptions,
        )
    
    return inner


async def render_geojson(
    datasette, columns, rows, sql, query_name, database, table, request, view_name, data
):
    lat_col, lon_col = find_spatial_columns(columns)
    
    if lat_col is None or lon_col is None:
        missing = []
        if lat_col is None:
            missing.append("latitude column (latitude, lat, y)")
        if lon_col is None:
            missing.append("longitude column (longitude, lon, lng, x)")
        raise BadRequest(f"Table is not spatial. Missing: {', '.join(missing)}")
    
    crs = request.args.get("_crs", "EPSG:4326")
    
    features = []
    for row in rows:
        if isinstance(row, dict):
            lat_val = row.get(lat_col)
            lon_val = row.get(lon_col)
            properties = {k: v for k, v in row.items() if k not in (lat_col, lon_col)}
        else:
            lat_idx = columns.index(lat_col)
            lon_idx = columns.index(lon_col)
            lat_val = row[lat_idx]
            lon_val = row[lon_idx]
            properties = {columns[i]: row[i] for i in range(len(columns)) if columns[i] not in (lat_col, lon_col)}
        
        try:
            lat = float(lat_val)
            lon = float(lon_val)
        except (TypeError, ValueError):
            continue
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": properties
        }
        features.append(feature)
    
    truncated = data.get("truncated") if data else None
    next_url = data.get("next_url") if data else None
    
    feature_collection = {
        "type": "FeatureCollection",
        "features": features
    }
    
    if truncated:
        feature_collection["truncated"] = True
    if next_url:
        feature_collection["next_url"] = next_url
    
    headers = {}
    if crs:
        headers["Content-CRS"] = crs
    
    return Response(
        body=json.dumps(feature_collection),
        status=200,
        headers=headers,
        content_type="application/geo+json; charset=utf-8"
    )


async def can_render_geojson(
    datasette, columns, rows, sql, query_name, database, table, request, view_name
):
    lat_col, lon_col = find_spatial_columns(columns)
    return lat_col is not None and lon_col is not None


@hookimpl
def register_output_renderer(datasette):
    return {
        "extension": "geojson",
        "render": render_geojson,
        "can_render": can_render_geojson,
    }
