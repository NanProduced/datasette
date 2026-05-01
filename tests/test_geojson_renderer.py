import json
import pytest
import pytest_asyncio
from datasette.app import Datasette
from datasette.database import Database
import secrets


@pytest_asyncio.fixture(scope="module")
async def geojson_ds_client():
    ds = Datasette(
        settings={
            "default_page_size": 50,
            "max_returned_rows": 100,
            "sql_time_limit_ms": 200,
            "num_sql_threads": 1,
        },
    )
    
    unique_memory_name = f"geojson_{secrets.token_hex(8)}"
    db = ds.add_database(Database(ds, memory_name=unique_memory_name), name="geojson")
    ds.remove_database("_memory")
    
    TABLES = """
    CREATE TABLE roadside_attractions (
        pk integer primary key,
        name text,
        address text,
        url text,
        latitude real,
        longitude real
    );
    INSERT INTO roadside_attractions VALUES (
        1, "The Mystery Spot", "465 Mystery Spot Road, Santa Cruz, CA 95065", "https://www.mysteryspot.com/",
        37.0167, -122.0024
    );
    INSERT INTO roadside_attractions VALUES (
        2, "Winchester Mystery House", "525 South Winchester Boulevard, San Jose, CA 95128", "https://winchestermysteryhouse.com/",
        37.3184, -121.9511
    );
    INSERT INTO roadside_attractions VALUES (
        3, "Burlingame Museum of PEZ Memorabilia", "214 California Drive, Burlingame, CA 94010", null,
        37.5793, -122.3442
    );
    INSERT INTO roadside_attractions VALUES (
        4, "Bigfoot Discovery Museum", "5497 Highway 9, Felton, CA 95018", "https://www.bigfootdiscoveryproject.com/",
        37.0414, -122.0725
    );
    
    CREATE TABLE large_spatial_table (
        pk integer primary key,
        name text,
        latitude real,
        longitude real
    );
    
    CREATE TABLE alt_columns (
        pk integer primary key,
        name text,
        lat real,
        lon real
    );
    INSERT INTO alt_columns VALUES (1, "Location A", 37.0, -122.0);
    INSERT INTO alt_columns VALUES (2, "Location B", 38.0, -121.0);
    
    CREATE TABLE xy_columns (
        pk integer primary key,
        name text,
        y real,
        x real
    );
    INSERT INTO xy_columns VALUES (1, "Point A", 37.0, -122.0);
    
    CREATE TABLE lng_columns (
        pk integer primary key,
        name text,
        latitude real,
        lng real
    );
    INSERT INTO lng_columns VALUES (1, "Test", 37.0, -122.0);
    
    CREATE TABLE non_spatial (
        pk integer primary key,
        name text,
        value text
    );
    INSERT INTO non_spatial VALUES (1, "Test", "Value");
    
    CREATE TABLE missing_lat (
        pk integer primary key,
        name text,
        longitude real
    );
    INSERT INTO missing_lat VALUES (1, "Test", -122.0);
    
    CREATE TABLE missing_lon (
        pk integer primary key,
        name text,
        latitude real
    );
    INSERT INTO missing_lon VALUES (1, "Test", 37.0);
    """
    
    def prepare(conn):
        if not conn.execute("select count(*) from sqlite_master").fetchone()[0]:
            conn.executescript(TABLES)
            cursor = conn.cursor()
            for i in range(200):
                if i < 50:
                    lat = 37.0 + (i * 0.001)
                    lon = -122.0 + (i * 0.001)
                elif i < 150:
                    lat = 40.0 + (i * 0.001)
                    lon = -120.0 + (i * 0.001)
                else:
                    lat = 37.1 + ((i - 150) * 0.001)
                    lon = -121.9 + ((i - 150) * 0.001)
                cursor.execute(
                    "INSERT INTO large_spatial_table (pk, name, latitude, longitude) VALUES (?, ?, ?, ?)",
                    (i + 1, f"Point {i + 1}", lat, lon)
                )
            conn.commit()
    
    await db.execute_write_fn(prepare)
    await ds.invoke_startup()
    return ds.client


@pytest.mark.asyncio
async def test_geojson_normal_output(geojson_ds_client):
    response = await geojson_ds_client.get("/geojson/roadside_attractions.geojson")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geo+json; charset=utf-8"
    
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 4
    
    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [-122.0024, 37.0167]
    
    assert "pk" in feature["properties"]
    assert "name" in feature["properties"]
    assert "latitude" not in feature["properties"]
    assert "longitude" not in feature["properties"]


@pytest.mark.asyncio
async def test_geojson_missing_columns_error(geojson_ds_client):
    response = await geojson_ds_client.get("/geojson/non_spatial.geojson")
    assert response.status_code == 400
    
    response2 = await geojson_ds_client.get("/geojson/missing_lat.geojson")
    assert response2.status_code == 400
    assert "latitude column" in response2.text
    
    response3 = await geojson_ds_client.get("/geojson/missing_lon.geojson")
    assert response3.status_code == 400
    assert "longitude column" in response3.text


@pytest.mark.asyncio
async def test_geojson_bbox_filter(geojson_ds_client):
    response = await geojson_ds_client.get("/geojson/roadside_attractions.geojson?_bbox=-122.5,36.5,-121.5,37.6")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["features"]) == 4
    
    response2 = await geojson_ds_client.get("/geojson/roadside_attractions.geojson?_bbox=-122.1,37.0,-121.9,37.1")
    data2 = response2.json()
    assert len(data2["features"]) == 2
    
    response3 = await geojson_ds_client.get("/geojson/roadside_attractions.geojson?_bbox=0,0,1,1")
    data3 = response3.json()
    assert len(data3["features"]) == 0


@pytest.mark.asyncio
async def test_geojson_column_aliases(geojson_ds_client):
    response = await geojson_ds_client.get("/geojson/alt_columns.geojson")
    assert response.status_code == 200
    data = response.json()
    assert len(data["features"]) == 2
    assert data["features"][0]["geometry"]["coordinates"] == [-122.0, 37.0]
    
    response2 = await geojson_ds_client.get("/geojson/xy_columns.geojson")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["features"]) == 1
    assert data2["features"][0]["geometry"]["coordinates"] == [-122.0, 37.0]
    
    response3 = await geojson_ds_client.get("/geojson/lng_columns.geojson")
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["features"]) == 1
    assert data3["features"][0]["geometry"]["coordinates"] == [-122.0, 37.0]


@pytest.mark.asyncio
async def test_geojson_crs_header(geojson_ds_client):
    response = await geojson_ds_client.get("/geojson/roadside_attractions.geojson")
    assert response.status_code == 200
    assert response.headers.get("content-crs") == "EPSG:4326"
    
    response2 = await geojson_ds_client.get("/geojson/roadside_attractions.geojson?_crs=EPSG:3857")
    assert response2.status_code == 200
    assert response2.headers.get("content-crs") == "EPSG:3857"
    
    response3 = await geojson_ds_client.get("/geojson/roadside_attractions.geojson?_crs=urn:ogc:def:crs:EPSG::4326")
    assert response3.status_code == 200
    assert response3.headers.get("content-crs") == "urn:ogc:def:crs:EPSG::4326"


@pytest.mark.asyncio
async def test_geojson_bbox_filter_sql_level(geojson_ds_client):
    response_no_bbox = await geojson_ds_client.get("/geojson/large_spatial_table.geojson?_size=100")
    assert response_no_bbox.status_code == 200
    data_no_bbox = response_no_bbox.json()
    assert len(data_no_bbox["features"]) == 100
    
    response_bbox = await geojson_ds_client.get(
        "/geojson/large_spatial_table.geojson?_bbox=-122.1,36.9,-121.8,37.2&_size=100"
    )
    assert response_bbox.status_code == 200
    data_bbox = response_bbox.json()
    
    assert len(data_bbox["features"]) == 100
    
    pks_in_bbox = [feature["properties"]["pk"] for feature in data_bbox["features"]]
    pks_in_bbox.sort()
    
    expected_pks = list(range(1, 51)) + list(range(151, 201))
    assert pks_in_bbox == expected_pks
    
    for feature in data_bbox["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert -122.1 <= lon <= -121.8
        assert 36.9 <= lat <= 37.2
