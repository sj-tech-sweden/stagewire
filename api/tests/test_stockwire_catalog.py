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
    if path == "/api/v1/inventory/products/with-availability":
        # Batch availability endpoint: same list, but each product carries availability for the
        # requested window. ``available_quantity`` here is the min available across the window.
        rows = PRODUCTS
        if "search" in params:
            rows = [r for r in rows if params["search"].lower() in r["name"].lower()]
        if "category" in params:
            rows = [r for r in rows if r["category"] == params["category"]]
        window = {1: 3, 2: 0, 3: 1}
        rows = [
            {
                **r,
                "total_quantity": window.get(r["id"], 0),
                "max_reserved_quantity": 0,
                "available_quantity": window.get(r["id"], 0),
            }
            for r in rows
        ]
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
    result = await client().search_catalog(start_date="2026-11-02", end_date="2026-11-04")
    by_name = {i["name"]: i for i in result["items"]}
    # availability endpoint, not the upstream current-stock count (which is 8 for SM58)
    assert by_name["SM58"]["available_qty"] == 3
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
async def test_search_uses_batch_with_availability_endpoint_and_no_per_product_calls():
    # Performance: with a rental window the catalog hits the batch ``with-availability`` endpoint,
    # which inlines availability on every product in a single sweep, instead of firing one
    # per-product availability call.
    per_product_calls = []
    with_availability_calls = []

    def counting_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/inventory/products/with-availability":
            with_availability_calls.append(1)
            rows = [
                {
                    "id": i,
                    "name": f"P{i}",
                    "eventory_available_qty": 5,
                    "total_quantity": 5,
                    "max_reserved_quantity": 0,
                    "available_quantity": 1,
                }
                for i in range(1, 11)
            ]
            return httpx.Response(200, json={"items": rows, "total": len(rows), "has_more": False})
        if path.startswith("/api/v1/inventory/products/") and path.endswith("/availability"):
            per_product_calls.append(int(path.split("/")[-2]))
            return httpx.Response(200, json={"available_quantity": 1})
        if path == "/api/v1/jobs/requirements":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"detail": "Not Found"})

    sw = StockwireClient(
        base_url="http://sw.test", token="t", transport=httpx.MockTransport(counting_handler)
    )
    result = await sw.search_catalog(start_date="2026-01-01", end_date="2026-01-02", limit=3)
    assert len(result["items"]) == 3
    assert all(i["available_qty"] == 1 for i in result["items"])
    assert len(with_availability_calls) == 1  # one batch sweep, not per product
    assert per_product_calls == []  # no per-product availability calls


@pytest.mark.asyncio
async def test_search_attribute_filter_and_paging():
    result = await client().search_catalog(attributes={"manufacturer": "shure"})
    assert [i["name"] for i in result["items"]] == ["SM58"]
    paged = await client().search_catalog(skip=1, limit=1)
    assert paged["total"] == 3 and [i["name"] for i in paged["items"]] == ["e935"]


@pytest.mark.asyncio
async def test_search_excludes_rental_products_by_default_but_can_include_them():
    # Rental-in products (e.g. from Eventory) are hidden unless the caller opts in. The upstream
    # flag is a pass-through, so we assert the client sends it and that the flag controls results.
    mixed = [
        {
            "id": 1,
            "name": "Own Mic",
            "category": "Microphones",
            "source": "own",
            "eventory_available_qty": 5,
        },
        {
            "id": 2,
            "name": "Rental Mic",
            "category": "Microphones",
            "source": "eventory",
            "eventory_available_qty": 2,
        },
    ]

    def mixed_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        excluded = str(params.get("exclude_rental", "True")).lower() != "false"
        rows = [r for r in mixed if not (excluded and r["source"] != "own")]
        return httpx.Response(200, json={"items": rows, "total": len(rows), "has_more": False})

    sw = StockwireClient(
        base_url="http://sw.test", token="t", transport=httpx.MockTransport(mixed_handler)
    )
    defaulted = await sw.search_catalog()
    assert [i["name"] for i in defaulted["items"]] == ["Own Mic"]
    included = await sw.search_catalog(exclude_rental=False)
    assert {i["name"] for i in included["items"]} == {"Own Mic", "Rental Mic"}


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
