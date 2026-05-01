from datasette.app import Datasette
from datasette.database import Database
from datasette.facets import Facet, ColumnFacet, ArrayFacet, DateFacet
from datasette.utils.asgi import Request
from datasette.utils import detect_json1
from .fixtures import make_app_client
import json
import pytest


@pytest.mark.asyncio
async def test_column_facet_suggest(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    suggestions = await facet.suggest()
    assert [
        {"name": "created", "toggle_url": "http://localhost/?_facet=created"},
        {"name": "planet_int", "toggle_url": "http://localhost/?_facet=planet_int"},
        {"name": "on_earth", "toggle_url": "http://localhost/?_facet=on_earth"},
        {"name": "state", "toggle_url": "http://localhost/?_facet=state"},
        {"name": "_city_id", "toggle_url": "http://localhost/?_facet=_city_id"},
        {
            "name": "_neighborhood",
            "toggle_url": "http://localhost/?_facet=_neighborhood",
        },
        {"name": "tags", "toggle_url": "http://localhost/?_facet=tags"},
        {
            "name": "complex_array",
            "toggle_url": "http://localhost/?_facet=complex_array",
        },
    ] == suggestions


@pytest.mark.asyncio
async def test_column_facet_suggest_skip_if_already_selected(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/?_facet=planet_int&_facet=on_earth"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    suggestions = await facet.suggest()
    assert [
        {
            "name": "created",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=created",
        },
        {
            "name": "state",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=state",
        },
        {
            "name": "_city_id",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=_city_id",
        },
        {
            "name": "_neighborhood",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=_neighborhood",
        },
        {
            "name": "tags",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=tags",
        },
        {
            "name": "complex_array",
            "toggle_url": "http://localhost/?_facet=planet_int&_facet=on_earth&_facet=complex_array",
        },
    ] == suggestions


@pytest.mark.asyncio
async def test_column_facet_suggest_skip_if_enabled_by_metadata(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
        table_config={"facets": ["_city_id"]},
    )
    suggestions = [s["name"] for s in await facet.suggest()]
    assert [
        "created",
        "planet_int",
        "on_earth",
        "state",
        "_neighborhood",
        "tags",
        "complex_array",
    ] == suggestions


@pytest.mark.asyncio
async def test_column_facet_results(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/?_facet=_city_id"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    buckets, timed_out = await facet.facet_results()
    assert [] == timed_out
    assert [
        {
            "name": "_city_id",
            "type": "column",
            "hideable": True,
            "toggle_url": "/",
            "results": [
                {
                    "value": 1,
                    "label": "San Francisco",
                    "count": 6,
                    "toggle_url": "http://localhost/?_facet=_city_id&_city_id__exact=1",
                    "selected": False,
                },
                {
                    "value": 2,
                    "label": "Los Angeles",
                    "count": 4,
                    "toggle_url": "http://localhost/?_facet=_city_id&_city_id__exact=2",
                    "selected": False,
                },
                {
                    "value": 3,
                    "label": "Detroit",
                    "count": 4,
                    "toggle_url": "http://localhost/?_facet=_city_id&_city_id__exact=3",
                    "selected": False,
                },
                {
                    "value": 4,
                    "label": "Memnonia",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_city_id&_city_id__exact=4",
                    "selected": False,
                },
            ],
            "truncated": False,
        }
    ] == buckets


@pytest.mark.asyncio
async def test_column_facet_results_column_starts_with_underscore(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/?_facet=_neighborhood"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    buckets, timed_out = await facet.facet_results()
    assert [] == timed_out
    assert buckets == [
        {
            "name": "_neighborhood",
            "type": "column",
            "hideable": True,
            "toggle_url": "/",
            "results": [
                {
                    "value": "Downtown",
                    "label": "Downtown",
                    "count": 2,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Downtown",
                    "selected": False,
                },
                {
                    "value": "Arcadia Planitia",
                    "label": "Arcadia Planitia",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Arcadia+Planitia",
                    "selected": False,
                },
                {
                    "value": "Bernal Heights",
                    "label": "Bernal Heights",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Bernal+Heights",
                    "selected": False,
                },
                {
                    "value": "Corktown",
                    "label": "Corktown",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Corktown",
                    "selected": False,
                },
                {
                    "value": "Dogpatch",
                    "label": "Dogpatch",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Dogpatch",
                    "selected": False,
                },
                {
                    "value": "Greektown",
                    "label": "Greektown",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Greektown",
                    "selected": False,
                },
                {
                    "value": "Hayes Valley",
                    "label": "Hayes Valley",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Hayes+Valley",
                    "selected": False,
                },
                {
                    "value": "Hollywood",
                    "label": "Hollywood",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Hollywood",
                    "selected": False,
                },
                {
                    "value": "Koreatown",
                    "label": "Koreatown",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Koreatown",
                    "selected": False,
                },
                {
                    "value": "Los Feliz",
                    "label": "Los Feliz",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Los+Feliz",
                    "selected": False,
                },
                {
                    "value": "Mexicantown",
                    "label": "Mexicantown",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Mexicantown",
                    "selected": False,
                },
                {
                    "value": "Mission",
                    "label": "Mission",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Mission",
                    "selected": False,
                },
                {
                    "value": "SOMA",
                    "label": "SOMA",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=SOMA",
                    "selected": False,
                },
                {
                    "value": "Tenderloin",
                    "label": "Tenderloin",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet=_neighborhood&_neighborhood__exact=Tenderloin",
                    "selected": False,
                },
            ],
            "truncated": False,
        }
    ]


@pytest.mark.asyncio
async def test_column_facet_from_metadata_cannot_be_hidden(ds_client):
    facet = ColumnFacet(
        ds_client.ds,
        Request.fake("/"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
        table_config={"facets": ["_city_id"]},
    )
    buckets, timed_out = await facet.facet_results()
    assert [] == timed_out
    assert [
        {
            "name": "_city_id",
            "type": "column",
            "hideable": False,
            "toggle_url": "/",
            "results": [
                {
                    "value": 1,
                    "label": "San Francisco",
                    "count": 6,
                    "toggle_url": "http://localhost/?_city_id__exact=1",
                    "selected": False,
                },
                {
                    "value": 2,
                    "label": "Los Angeles",
                    "count": 4,
                    "toggle_url": "http://localhost/?_city_id__exact=2",
                    "selected": False,
                },
                {
                    "value": 3,
                    "label": "Detroit",
                    "count": 4,
                    "toggle_url": "http://localhost/?_city_id__exact=3",
                    "selected": False,
                },
                {
                    "value": 4,
                    "label": "Memnonia",
                    "count": 1,
                    "toggle_url": "http://localhost/?_city_id__exact=4",
                    "selected": False,
                },
            ],
            "truncated": False,
        }
    ] == buckets


@pytest.mark.asyncio
@pytest.mark.skipif(not detect_json1(), reason="Requires the SQLite json1 module")
async def test_array_facet_suggest(ds_client):
    facet = ArrayFacet(
        ds_client.ds,
        Request.fake("/"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    suggestions = await facet.suggest()
    assert [
        {
            "name": "tags",
            "type": "array",
            "toggle_url": "http://localhost/?_facet_array=tags",
        }
    ] == suggestions


@pytest.mark.asyncio
@pytest.mark.skipif(not detect_json1(), reason="Requires the SQLite json1 module")
async def test_array_facet_suggest_not_if_all_empty_arrays(ds_client):
    facet = ArrayFacet(
        ds_client.ds,
        Request.fake("/"),
        database="fixtures",
        sql="select * from facetable where tags = '[]'",
        table="facetable",
    )
    suggestions = await facet.suggest()
    assert [] == suggestions


@pytest.mark.asyncio
@pytest.mark.skipif(not detect_json1(), reason="Requires the SQLite json1 module")
async def test_array_facet_results(ds_client):
    facet = ArrayFacet(
        ds_client.ds,
        Request.fake("/?_facet_array=tags"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    buckets, timed_out = await facet.facet_results()
    assert [] == timed_out
    assert [
        {
            "name": "tags",
            "type": "array",
            "results": [
                {
                    "value": "tag1",
                    "label": "tag1",
                    "count": 2,
                    "toggle_url": "http://localhost/?_facet_array=tags&tags__arraycontains=tag1",
                    "selected": False,
                },
                {
                    "value": "tag2",
                    "label": "tag2",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet_array=tags&tags__arraycontains=tag2",
                    "selected": False,
                },
                {
                    "value": "tag3",
                    "label": "tag3",
                    "count": 1,
                    "toggle_url": "http://localhost/?_facet_array=tags&tags__arraycontains=tag3",
                    "selected": False,
                },
            ],
            "hideable": True,
            "toggle_url": "/",
            "truncated": False,
        }
    ] == buckets


@pytest.mark.asyncio
@pytest.mark.skipif(not detect_json1(), reason="Requires the SQLite json1 module")
async def test_array_facet_handle_duplicate_tags():
    ds = Datasette([], memory=True)
    db = ds.add_database(Database(ds, memory_name="test_array_facet"))
    await db.execute_write("create table otters(name text, tags text)")
    for name, tags in (
        ("Charles", ["friendly", "cunning", "friendly"]),
        ("Shaun", ["cunning", "empathetic", "friendly"]),
        ("Tracy", ["empathetic", "eager"]),
    ):
        await db.execute_write(
            "insert into otters (name, tags) values (?, ?)", [name, json.dumps(tags)]
        )

    response = await ds.client.get("/test_array_facet/otters.json?_facet_array=tags")
    assert response.json()["facet_results"]["results"]["tags"] == {
        "name": "tags",
        "type": "array",
        "results": [
            {
                "value": "cunning",
                "label": "cunning",
                "count": 2,
                "toggle_url": "http://localhost/test_array_facet/otters.json?_facet_array=tags&tags__arraycontains=cunning",
                "selected": False,
            },
            {
                "value": "empathetic",
                "label": "empathetic",
                "count": 2,
                "toggle_url": "http://localhost/test_array_facet/otters.json?_facet_array=tags&tags__arraycontains=empathetic",
                "selected": False,
            },
            {
                "value": "friendly",
                "label": "friendly",
                "count": 2,
                "toggle_url": "http://localhost/test_array_facet/otters.json?_facet_array=tags&tags__arraycontains=friendly",
                "selected": False,
            },
            {
                "value": "eager",
                "label": "eager",
                "count": 1,
                "toggle_url": "http://localhost/test_array_facet/otters.json?_facet_array=tags&tags__arraycontains=eager",
                "selected": False,
            },
        ],
        "hideable": True,
        "toggle_url": "/test_array_facet/otters.json",
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_date_facet_results(ds_client):
    facet = DateFacet(
        ds_client.ds,
        Request.fake("/?_facet_date=created"),
        database="fixtures",
        sql="select * from facetable",
        table="facetable",
    )
    buckets, timed_out = await facet.facet_results()
    assert [] == timed_out
    assert [
        {
            "name": "created",
            "type": "date",
            "results": [
                {
                    "value": "2019-01-14",
                    "label": "2019-01-14",
                    "count": 4,
                    "toggle_url": "http://localhost/?_facet_date=created&created__date=2019-01-14",
                    "selected": False,
                },
                {
                    "value": "2019-01-15",
                    "label": "2019-01-15",
                    "count": 4,
                    "toggle_url": "http://localhost/?_facet_date=created&created__date=2019-01-15",
                    "selected": False,
                },
                {
                    "value": "2019-01-17",
                    "label": "2019-01-17",
                    "count": 4,
                    "toggle_url": "http://localhost/?_facet_date=created&created__date=2019-01-17",
                    "selected": False,
                },
                {
                    "value": "2019-01-16",
                    "label": "2019-01-16",
                    "count": 3,
                    "toggle_url": "http://localhost/?_facet_date=created&created__date=2019-01-16",
                    "selected": False,
                },
            ],
            "hideable": True,
            "toggle_url": "/",
            "truncated": False,
        }
    ] == buckets


@pytest.mark.asyncio
async def test_json_array_with_blanks_and_nulls():
    ds = Datasette([], memory=True)
    db = ds.add_database(Database(ds, memory_name="test_json_array"))
    await db.execute_write("create table foo(json_column text)")
    for value in ('["a", "b", "c"]', '["a", "b"]', "", None):
        await db.execute_write("insert into foo (json_column) values (?)", [value])
    response = await ds.client.get("/test_json_array/foo.json?_extra=suggested_facets")
    data = response.json()
    assert data["suggested_facets"] == [
        {
            "name": "json_column",
            "type": "array",
            "toggle_url": "http://localhost/test_json_array/foo.json?_extra=suggested_facets&_facet_array=json_column",
        }
    ]


@pytest.mark.asyncio
async def test_facet_size():
    ds = Datasette([], memory=True, settings={"max_returned_rows": 50})
    db = ds.add_database(Database(ds, memory_name="test_facet_size"))
    await db.execute_write("create table neighbourhoods(city text, neighbourhood text)")
    for i in range(1, 51):
        for j in range(1, 4):
            await db.execute_write(
                "insert into neighbourhoods (city, neighbourhood) values (?, ?)",
                ["City {}".format(i), "Neighbourhood {}".format(j)],
            )
    response = await ds.client.get(
        "/test_facet_size/neighbourhoods.json?_extra=suggested_facets"
    )
    data = response.json()
    assert data["suggested_facets"] == [
        {
            "name": "neighbourhood",
            "toggle_url": "http://localhost/test_facet_size/neighbourhoods.json?_extra=suggested_facets&_facet=neighbourhood",
        }
    ]
    # Bump up _facet_size= to suggest city too
    response2 = await ds.client.get(
        "/test_facet_size/neighbourhoods.json?_facet_size=50&_extra=suggested_facets"
    )
    data2 = response2.json()
    assert sorted(data2["suggested_facets"], key=lambda f: f["name"]) == [
        {
            "name": "city",
            "toggle_url": "http://localhost/test_facet_size/neighbourhoods.json?_facet_size=50&_extra=suggested_facets&_facet=city",
        },
        {
            "name": "neighbourhood",
            "toggle_url": "http://localhost/test_facet_size/neighbourhoods.json?_facet_size=50&_extra=suggested_facets&_facet=neighbourhood",
        },
    ]
    # Facet by city should return expected number of results
    response3 = await ds.client.get(
        "/test_facet_size/neighbourhoods.json?_facet_size=50&_facet=city"
    )
    data3 = response3.json()
    assert len(data3["facet_results"]["results"]["city"]["results"]) == 50
    # Reduce max_returned_rows and check that it's respected
    ds._settings["max_returned_rows"] = 20
    response4 = await ds.client.get(
        "/test_facet_size/neighbourhoods.json?_facet_size=50&_facet=city"
    )
    data4 = response4.json()
    assert len(data4["facet_results"]["results"]["city"]["results"]) == 20
    # Test _facet_size=max
    response5 = await ds.client.get(
        "/test_facet_size/neighbourhoods.json?_facet_size=max&_facet=city"
    )
    data5 = response5.json()
    assert len(data5["facet_results"]["results"]["city"]["results"]) == 20
    # Now try messing with facet_size in the table metadata
    orig_config = ds.config
    try:
        ds.config = {
            "databases": {
                "test_facet_size": {"tables": {"neighbourhoods": {"facet_size": 6}}}
            }
        }
        response6 = await ds.client.get(
            "/test_facet_size/neighbourhoods.json?_facet=city"
        )
        data6 = response6.json()
        assert len(data6["facet_results"]["results"]["city"]["results"]) == 6
        # Setting it to max bumps it up to 50 again
        ds.config["databases"]["test_facet_size"]["tables"]["neighbourhoods"][
            "facet_size"
        ] = "max"
        data7 = (
            await ds.client.get("/test_facet_size/neighbourhoods.json?_facet=city")
        ).json()
        assert len(data7["facet_results"]["results"]["city"]["results"]) == 20
    finally:
        ds.config = orig_config


def test_other_types_of_facet_in_metadata():
    with make_app_client(
        metadata={
            "databases": {
                "fixtures": {
                    "tables": {
                        "facetable": {
                            "facets": ["state", {"array": "tags"}, {"date": "created"}]
                        }
                    }
                }
            }
        }
    ) as client:
        response = client.get("/fixtures/facetable")
        fragments = (
            "<strong>state\n",
            "<strong>tags (array)\n",
            "<strong>created (date)\n",
        )
        for fragment in fragments:
            assert fragment in response.text
        # Verify they appear in the metadata-defined order
        positions = [response.text.index(f) for f in fragments]
        assert positions == sorted(
            positions
        ), "Facets should appear in metadata-defined order"


def test_metadata_facet_ordering():
    with make_app_client(
        metadata={
            "databases": {
                "fixtures": {
                    "tables": {
                        "facetable": {
                            "facets": ["state", {"array": "tags"}, {"date": "created"}]
                        }
                    }
                }
            }
        }
    ) as client:
        # JSON response should have facets in the metadata-defined order
        response = client.get("/fixtures/facetable.json?_extra=sorted_facet_results")
        data = response.json
        facet_names = [f["name"] for f in data["sorted_facet_results"]]
        assert facet_names == ["state", "tags", "created"]

        # With an additional request-based facet, metadata facets come first
        # in their defined order, followed by request-based facets
        response2 = client.get(
            "/fixtures/facetable.json?_extra=sorted_facet_results&_facet=_city_id"
        )
        data2 = response2.json
        facet_names2 = [f["name"] for f in data2["sorted_facet_results"]]
        assert facet_names2 == ["state", "tags", "created", "_city_id"]


@pytest.mark.asyncio
async def test_conflicting_facet_names_json(ds_client):
    response = await ds_client.get(
        "/fixtures/facetable.json?_facet=created&_facet_date=created"
        "&_facet=tags&_facet_array=tags"
    )
    assert set(response.json()["facet_results"]["results"].keys()) == {
        "created",
        "tags",
        "created_2",
        "tags_2",
    }


@pytest.mark.asyncio
async def test_facet_against_in_memory_database():
    ds = Datasette()
    db = ds.add_memory_database("mem")
    await db.execute_write(
        "create table t (id integer primary key, name text, name2 text)"
    )
    to_insert = [{"name": "one", "name2": "1"} for _ in range(800)] + [
        {"name": "two", "name2": "2"} for _ in range(300)
    ]
    await db.execute_write_many(
        "insert into t (name, name2) values (:name, :name2)", to_insert
    )
    response1 = await ds.client.get("/mem/t")
    assert response1.status_code == 200
    response2 = await ds.client.get("/mem/t?_facet=name&_facet=name2")
    assert response2.status_code == 200


@pytest.mark.asyncio
async def test_facet_only_considers_first_x_rows():
    # This test works by manually fiddling with Facet.suggest_consider
    ds = Datasette()
    original_suggest_consider = Facet.suggest_consider
    try:
        Facet.suggest_consider = 40
        db = ds.add_memory_database("test_facet_only_x_rows")
        await db.execute_write("create table t (id integer primary key, col text)")
        # First 50 rows make it look like col and col_json should be faceted
        to_insert = [{"col": "one" if i % 2 else "two"} for i in range(50)]
        await db.execute_write_many("insert into t (col) values (:col)", to_insert)
        # Next 50 break that assumption
        to_insert2 = [{"col": f"x{i}"} for i in range(50)]
        await db.execute_write_many("insert into t (col) values (:col)", to_insert2)
        response = await ds.client.get(
            "/test_facet_only_x_rows/t.json?_extra=suggested_facets"
        )
        data = response.json()
        assert data["suggested_facets"] == [
            {
                "name": "col",
                "toggle_url": "http://localhost/test_facet_only_x_rows/t.json?_extra=suggested_facets&_facet=col",
            }
        ]
        # But if we set suggest_consider to 100 they are not suggested
        Facet.suggest_consider = 100
        response2 = await ds.client.get(
            "/test_facet_only_x_rows/t.json?_extra=suggested_facets"
        )
        data2 = response2.json()
        assert data2["suggested_facets"] == []
    finally:
        Facet.suggest_consider = original_suggest_consider


from datasette.facets import (
    freedman_diaconis_bin_width,
    round_bin_edges,
    calculate_bins,
    HistogramFacet,
)


def test_freedman_diaconis_bin_width():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    h = freedman_diaconis_bin_width(values)
    assert h is not None
    assert h > 0


def test_freedman_diaconis_bin_width_insufficient_data():
    assert freedman_diaconis_bin_width([]) is None
    assert freedman_diaconis_bin_width([1]) is None


def test_freedman_diaconis_bin_width_same_values():
    assert freedman_diaconis_bin_width([5, 5, 5, 5]) is None


def test_round_bin_edges():
    start, end, num_bins, width = round_bin_edges(1, 10, 2)
    assert start == 0
    assert end == 10
    assert width == 2
    assert num_bins == 5


def test_round_bin_edges_small_values():
    start, end, num_bins, width = round_bin_edges(0.1, 0.9, 0.15)
    assert start <= 0.1
    assert end >= 0.9
    assert width in (0.1, 0.2)
    assert num_bins >= 4


def test_calculate_bins_freedman_diaconis():
    values = list(range(1, 101))
    bins = calculate_bins(1, 100, values)
    assert bins is not None
    assert len(bins) > 0
    for start, end in bins:
        assert start < end


def test_calculate_bins_single_value():
    bins = calculate_bins(5, 5, [5])
    assert bins == [(5, 6)]


def test_calculate_bins_none():
    assert calculate_bins(None, 10) is None
    assert calculate_bins(10, None) is None


@pytest.mark.asyncio
async def test_histogram_facet_suggest():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_suggest")
    await db.execute_write(
        "create table products (id integer primary key, price integer, name text)"
    )
    for i in range(20):
        await db.execute_write(
            "insert into products (price, name) values (?, ?)",
            [i * 10, f"Product {i}"],
        )
    response = await ds.client.get(
        "/test_histogram_suggest/products.json?_extra=suggested_facets"
    )
    data = response.json()
    histogram_facets = [
        f for f in data["suggested_facets"] if f.get("type") == "histogram"
    ]
    assert len(histogram_facets) == 1
    assert histogram_facets[0]["name"] == "price"
    assert "_facet_histogram=price" in histogram_facets[0]["toggle_url"]


@pytest.mark.asyncio
async def test_histogram_facet_results():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_results")
    await db.execute_write(
        "create table ages (id integer primary key, age integer)"
    )
    ages = [18, 22, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 25, 30, 35, 40, 45, 50]
    for age in ages:
        await db.execute_write("insert into ages (age) values (?)", [age])
    response = await ds.client.get(
        "/test_histogram_results/ages.json?_facet_histogram=age"
    )
    data = response.json()
    assert "age" in data["facet_results"]["results"]
    age_facet = data["facet_results"]["results"]["age"]
    assert age_facet["type"] == "histogram"
    assert "results" in age_facet
    assert len(age_facet["results"]) > 0
    total_count = sum(r["count"] for r in age_facet["results"])
    assert total_count == len(ages)
    for bin_result in age_facet["results"]:
        assert "bin_start" in bin_result
        assert "bin_end" in bin_result
        assert "label" in bin_result
        assert "toggle_url" in bin_result
        assert bin_result["bin_start"] < bin_result["bin_end"]


@pytest.mark.asyncio
async def test_histogram_facet_null_values():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_nulls")
    await db.execute_write(
        "create table temps (id integer primary key, temperature real)"
    )
    temps = [20.5, 22.3, None, 25.1, None, 18.9, None, 30.2]
    for temp in temps:
        await db.execute_write("insert into temps (temperature) values (?)", [temp])
    response = await ds.client.get(
        "/test_histogram_nulls/temps.json?_facet_histogram=temperature"
    )
    data = response.json()
    temp_facet = data["facet_results"]["results"]["temperature"]
    assert temp_facet["null_count"] == 3
    non_null_count = sum(r["count"] for r in temp_facet["results"])
    assert non_null_count == 5


@pytest.mark.asyncio
async def test_histogram_facet_filter_by_bin():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_filter")
    await db.execute_write(
        "create table salaries (id integer primary key, salary integer)"
    )
    salaries = [30000, 35000, 40000, 45000, 50000, 55000, 60000, 65000, 70000, 75000]
    for sal in salaries:
        await db.execute_write("insert into salaries (salary) values (?)", [sal])
    facet_response = await ds.client.get(
        "/test_histogram_filter/salaries.json?_facet_histogram=salary"
    )
    facet_data = facet_response.json()
    salary_facet = facet_data["facet_results"]["results"]["salary"]
    assert len(salary_facet["results"]) > 0
    first_bin = salary_facet["results"][0]
    assert "toggle_url" in first_bin
    assert not first_bin["selected"]
    filter_response = await ds.client.get(
        f"/test_histogram_filter/salaries.json?_facet_histogram=salary&salary__gte={first_bin['bin_start']}&salary__lt={first_bin['bin_end']}"
    )
    filter_data = filter_response.json()
    filtered_facet = filter_data["facet_results"]["results"]["salary"]
    selected_bins = [r for r in filtered_facet["results"] if r["selected"]]
    assert len(selected_bins) >= 1


@pytest.mark.asyncio
async def test_histogram_facet_all_nulls():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_all_nulls")
    await db.execute_write(
        "create table all_nulls (id integer primary key, value integer)"
    )
    for _ in range(5):
        await db.execute_write("insert into all_nulls (value) values (null)")
    response = await ds.client.get(
        "/test_histogram_all_nulls/all_nulls.json?_facet_histogram=value"
    )
    data = response.json()
    value_facet = data["facet_results"]["results"]["value"]
    assert value_facet["null_count"] == 5
    assert len(value_facet["results"]) == 0


@pytest.mark.asyncio
async def test_histogram_facet_real_numbers():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_reals")
    await db.execute_write(
        "create table measurements (id integer primary key, value real)"
    )
    import random
    random.seed(42)
    for _ in range(100):
        value = random.gauss(50, 10)
        await db.execute_write("insert into measurements (value) values (?)", [value])
    response = await ds.client.get(
        "/test_histogram_reals/measurements.json?_facet_histogram=value"
    )
    data = response.json()
    value_facet = data["facet_results"]["results"]["value"]
    assert len(value_facet["results"]) > 0
    assert value_facet["min_val"] is not None
    assert value_facet["max_val"] is not None
    assert value_facet["max_bin_count"] > 0
    total_count = sum(r["count"] for r in value_facet["results"])
    assert total_count == 100


@pytest.mark.asyncio
async def test_histogram_facet_from_metadata():
    ds = Datasette(
        [],
        memory=True,
        config={
            "databases": {
                "test_histogram_metadata": {
                    "tables": {
                        "items": {
                            "facets": [{"histogram": "quantity"}]
                        }
                    }
                }
            }
        }
    )
    db = ds.add_memory_database("test_histogram_metadata")
    await db.execute_write(
        "create table items (id integer primary key, quantity integer, name text)"
    )
    for i in range(10):
        await db.execute_write(
            "insert into items (quantity, name) values (?, ?)",
            [i * 5, f"Item {i}"],
        )
    response = await ds.client.get("/test_histogram_metadata/items.json")
    data = response.json()
    assert "quantity" in data["facet_results"]["results"]
    quantity_facet = data["facet_results"]["results"]["quantity"]
    assert quantity_facet["type"] == "histogram"
    assert quantity_facet["hideable"] == False


@pytest.mark.asyncio
async def test_histogram_facet_with_existing_column_facet():
    ds = Datasette()
    db = ds.add_memory_database("test_histogram_conflict")
    await db.execute_write(
        "create table data (id integer primary key, value integer)"
    )
    for i in range(20):
        await db.execute_write("insert into data (value) values (?)", [i % 5])
    response = await ds.client.get(
        "/test_histogram_conflict/data.json?_facet=value&_facet_histogram=value"
    )
    data = response.json()
    assert "value" in data["facet_results"]["results"]
    assert "value_2" in data["facet_results"]["results"]
