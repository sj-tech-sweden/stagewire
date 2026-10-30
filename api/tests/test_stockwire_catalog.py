import httpx
import pytest

from app.domains.stockwire.client import StockwireClient

PRODUCTS = [
    {
        "id": 1,
        "name": "SM58",
        "category": "Microphones",
        "manufacturer": "Shure",
        "eventory_available_qty": 8,
    },
    {
        "id": 2,
        "name": "e935",
        "category": "Microphones",
        "manufacturer": "Sennheiser",
        "eventory_available_qty": 4,
    },
    {
        "id": 3,
        "name": "Matrix",
        "category": "Video",
        "manufacturer": "Blackmagic Design",
        "eventory_available_qty": 1,
    },
]
DEVICES = [
    {"id": 10, "product_id": 1, "case_device_id": None},
    {"id": 11, "product_id": 2, "case_device_id": 99},
    {"id": 12, "product_id": 3, "case_device_id": 99},
    {"id": 13, "product_id": 1, "case_device_id": 5},
]
REQUIREMENTS = [
    {"job_id": 7, "product_id": 1, "quantity_required": 2},
    {"job_id": 7, "product_id": 1, "quantity_required": 1},
    {"job_id": 8, "product_id": 3, "quantity_required": 4},
]


def handler(request: httpx.Request) -> httpx.Response:
    """Mirrors the dev Stockwire: ignores case_device_id and job_id query filters."""
    path, params = request.url.path, dict(request.url.params)
    if path == "/api/v1/inventory/products":
        rows = PRODUCTS
        if "search" in params:
            rows = [r for r in rows if params["search"].lower() in r["name"].lower()]
        if "category" in params:
            rows = [r for r in rows if r["category"] == params["category"]]
        return httpx.Response(200, json={"items": rows, "total": len(rows), "has_more": False})
    if path.startswith("/api/v1/inventory/products/"):
        pid = int(path.rsplit("/", 1)[1])
        return httpx.Response(200, json=next(r for r in PRODUCTS if r["id"] == pid))
    if path == "/api/v1/inventory/devices":
        return httpx.Response(
            200, json={"items": DEVICES, "total": len(DEVICES), "has_more": False}
        )
    if path == "/api/v1/jobs/requirements":
        return httpx.Response(200, json=REQUIREMENTS)
    return httpx.Response(404, json={"detail": "Not Found"})


def client() -> StockwireClient:
    return StockwireClient(
        base_url="http://sw.test", token="t", transport=httpx.MockTransport(handler)
    )


@pytest.mark.asyncio
async def test_search_filters_multi_value_facets_locally_and_returns_counts():
    result = await client().search_catalog(
        categories=["Microphones", "Video"], manufacturers=["Shure", "Blackmagic Design"]
    )
    assert [i["name"] for i in result["items"]] == ["SM58", "Matrix"]
    assert result["facets"]["category"] == {"Microphones": 2, "Video": 1}
    assert result["availability"] == {"date_range_supported": False}


@pytest.mark.asyncio
async def test_search_marks_items_booked_on_the_job_only():
    result = await client().search_catalog(job_id="7")
    by_name = {i["name"]: i for i in result["items"]}
    assert by_name["SM58"]["booked"] is True and by_name["SM58"]["booked_qty"] == 3
    assert by_name["Matrix"]["booked"] is False
    assert by_name["SM58"]["available_qty"] == 8
    unbooked = await client().search_catalog()
    assert unbooked["items"][0]["booked"] is None


@pytest.mark.asyncio
async def test_search_attribute_filter_and_paging():
    result = await client().search_catalog(attributes={"manufacturer": "shure"})
    assert [i["name"] for i in result["items"]] == ["SM58"]
    paged = await client().search_catalog(skip=1, limit=1)
    assert paged["total"] == 3 and [i["name"] for i in paged["items"]] == ["e935"]


@pytest.mark.asyncio
async def test_case_children_are_selected_client_side_with_product_summary():
    children = await client().list_child_devices(99)
    assert [c["id"] for c in children] == [11, 12]
    assert children[0]["product"]["name"] == "e935"
    assert await client().list_child_devices(12345) == []
