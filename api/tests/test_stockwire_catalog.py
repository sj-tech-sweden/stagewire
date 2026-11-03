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
    {"id": 99, "product_id": 3, "case_device_id": None},
    {"id": 5, "product_id": 1, "case_device_id": None},
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
    if path.startswith("/api/v1/inventory/products/") and path.endswith("/availability"):
        pid = int(path.split("/")[-2])
        # Min available across the requested window, per product.
        avail = {1: 3, 2: 0, 3: 1}.get(pid, 0)
        return httpx.Response(
            200,
            json={
                "product_id": pid,
                "start_date": params.get("start_date"),
                "end_date": params.get("end_date"),
                "total_quantity": avail,
                "max_reserved_quantity": 0,
                "available_quantity": avail,
            },
        )
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
async def test_search_uses_date_ranged_availability_when_window_supplied():
    # With a rental window the available_qty comes from the availability endpoint (min across the
    # range), not the upstream current-stock count, and the catalog reports date support.
    result = await client().search_catalog(
        start_date="2026-11-02", end_date="2026-11-04"
    )
    by_name = {i["name"]: i for i in result["items"]}
    assert by_name["SM58"]["available_qty"] == 3  # availability endpoint, not eventory_available_qty (8)
    assert by_name["e935"]["available_qty"] == 0
    assert by_name["Matrix"]["available_qty"] == 1
    assert result["availability"] == {"date_range_supported": True}


@pytest.mark.asyncio
async def test_search_falls_back_to_current_stock_when_no_window():
    result = await client().search_catalog()
    by_name = {i["name"]: i for i in result["items"]}
    assert by_name["SM58"]["available_qty"] == 8  # current stock
    assert result["availability"] == {"date_range_supported": False}


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


@pytest.mark.asyncio
async def test_cases_are_devices_that_other_devices_point_at():
    cases = await client().list_cases()
    assert {(c["id"], c["child_count"]) for c in cases} == {(99, 2), (5, 1)}
    assert {c["id"]: c["name"] for c in cases}[99] == "Matrix"


@pytest.mark.asyncio
async def test_search_reports_when_the_catalog_was_cut_short():
    def handler_many(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params.get("skip", 0))
        page = [{"id": skip + i, "name": f"P{skip + i}"} for i in range(200)]
        return httpx.Response(200, json={"items": page, "total": 5000, "has_more": True})

    sw = StockwireClient(
        base_url="http://sw.test", token="t", transport=httpx.MockTransport(handler_many)
    )
    result = await sw.search_catalog(limit=5)
    assert result["truncated"] is True and result["total"] == 2000
    assert (await client().search_catalog())["truncated"] is False


@pytest.mark.asyncio
async def test_own_products_are_products_with_devices_and_the_device_count_is_the_quantity():
    result = await client().search_own_products()
    assert {p["id"]: p["device_count"] for p in result["items"]} == {1: 3, 2: 1, 3: 2}
    assert all(p["available_qty"] == p["device_count"] for p in result["items"])
    narrowed = await client().search_own_products(q="sm")
    assert [p["name"] for p in narrowed["items"]] == ["SM58"]
    assert (await client().search_own_products(limit=1))["total"] == 3
    assert len((await client().search_own_products(limit=1))["items"]) == 1
