import asyncio
import time

import httpx

from app.core.config import get_settings


def rental_job_payload(job) -> dict:
    """Map a Stagewire production job onto stockwire-rental's JobCreate schema."""
    code = f"SW-{str(job.id).replace('-', '')[:8].upper()}"
    payload: dict = {
        "job_code": code,
        "description": job.title or None,
        "venue_name": job.venue_name or None,
        "notes": job.notes or None,
        "status": "draft",
    }
    event_date = getattr(job, "event_date", None)
    if event_date:
        day = event_date.date() if hasattr(event_date, "date") else event_date
        payload["start_date"] = day.isoformat() if hasattr(day, "isoformat") else str(day)
    return payload


CACHE_TTL_SECONDS = 60.0
_PAGE_CACHE: dict[tuple, tuple[float, list[dict]]] = {}


class StockwireClient:
    """Thin async client for the Stockwire Rental API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._transport = transport
        self.truncated = False
        settings = get_settings()
        self.base_url = (base_url or settings.stockwire_api_base_url).rstrip("/")
        self.token = token or settings.stockwire_api_token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_job(self, job_id: str) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get(f"/api/v1/jobs/{job_id}")
            response.raise_for_status()
            return response.json()

    async def get_rental_job(self, job_id: int | str) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get(f"/api/v1/jobs/{job_id}")
            response.raise_for_status()
            return response.json()

    async def search_rental_jobs(self, search: str | None, limit: int = 20) -> dict:
        params: dict[str, object] = {"limit": limit}
        if search:
            params["search"] = search
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get("/api/v1/jobs", params=params)
            response.raise_for_status()
            return response.json()

    async def create_job(self, payload: dict) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.post("/api/v1/jobs", json=payload)
            if response.status_code >= 400:
                body = response.text[:400]
                raise RuntimeError(f"HTTP {response.status_code} from stockwire-rental: {body}")
            return response.json()

    async def search_products(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
        category_id: int | None = None,
        brand: str | None = None,
        manufacturer: str | None = None,
        exclude_rental: bool = False,
        min_inputs: int | None = None,
        min_outputs: int | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        params: dict[str, object] = {
            "skip": skip,
            "limit": limit,
            "exclude_rental": exclude_rental,
        }
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        if category_id is not None:
            params["category_id"] = category_id
        if brand:
            params["brand"] = brand
        if manufacturer:
            params["manufacturer"] = manufacturer
        if min_inputs is not None:
            params["min_inputs"] = min_inputs
        if min_outputs is not None:
            params["min_outputs"] = min_outputs
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get("/api/v1/inventory/products", params=params)
            response.raise_for_status()
            return response.json()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=15.0,
            transport=self._transport,
        )

    async def _all_pages(self, path: str, params: dict[str, object], cap: int = 2000) -> list[dict]:
        """Collect every page of a list endpoint (``{items, total, has_more}`` envelope).

        Results are cached for a minute (typeahead searches would otherwise refetch the whole
        catalog per keystroke); ``self.truncated`` is set when the cap cuts the list short.
        """
        key = (self.base_url, hash(self.token), path, tuple(sorted(params.items())))
        cached = _PAGE_CACHE.get(key) if self._transport is None else None
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        rows: list[dict] = []
        async with self._client() as client:
            while len(rows) < cap:
                response = await client.get(
                    path, params={**params, "skip": len(rows), "limit": 200}
                )
                response.raise_for_status()
                body = response.json()
                page = body if isinstance(body, list) else body.get("items", [])
                rows.extend(page)
                if not page or isinstance(body, list) or not body.get("has_more"):
                    break
            else:
                self.truncated = True
        if self._transport is None:
            _PAGE_CACHE[key] = (time.monotonic(), rows)
        return rows

    async def _product_names(self, product_ids: set[str]) -> dict[str, dict]:
        async with self._client() as client:

            async def fetch(pid: str) -> tuple[str, dict | None]:
                response = await client.get(f"/api/v1/inventory/products/{pid}")
                return pid, response.json() if response.status_code == 200 else None

            found = await asyncio.gather(*(fetch(pid) for pid in product_ids))
        return {pid: body for pid, body in found if body is not None}

    async def booked_quantities(self, stockwire_job_id: str | int) -> dict[str, int]:
        """product_id -> quantity required on a rental job.

        The upstream ``job_id`` filter on ``/jobs/requirements`` is ignored, so rows are
        filtered here.
        """
        async with self._client() as client:
            response = await client.get(
                "/api/v1/jobs/requirements", params={"job_id": stockwire_job_id}
            )
            response.raise_for_status()
            body = response.json()
        rows = body if isinstance(body, list) else body.get("items", [])
        booked: dict[str, int] = {}
        for row in rows:
            if str(row.get("job_id")) == str(stockwire_job_id):
                pid = str(row["product_id"])
                booked[pid] = booked.get(pid, 0) + int(row.get("quantity_required") or 0)
        return booked

    async def search_catalog(
        self,
        *,
        q: str | None = None,
        categories: list[str] | None = None,
        manufacturers: list[str] | None = None,
        attributes: dict[str, str] | None = None,
        job_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Faceted global catalog search over ``GET /api/v1/inventory/products``.

        Not limited to items booked on the job. The upstream only filters on one value per
        facet and has no attribute filters, no facet counts and no date-ranged availability
        (only ``eventory_available_qty``), so multi-value facets, ``attributes`` and the facet
        counts are computed here over the search result. ``job_id`` (a rental job id) marks
        each hit with the quantity already booked.
        """
        params: dict[str, object] = {}
        if q:
            params["search"] = q
        if categories and len(categories) == 1:
            params["category"] = categories[0]
        if manufacturers and len(manufacturers) == 1:
            params["manufacturer"] = manufacturers[0]
        rows = await self._all_pages("/api/v1/inventory/products", params)

        def facet(field: str) -> dict[str, int]:
            counts: dict[str, int] = {}
            for row in rows:
                value = row.get(field)
                if value:
                    counts[value] = counts.get(value, 0) + 1
            return dict(sorted(counts.items()))

        facets = {"category": facet("category"), "manufacturer": facet("manufacturer")}
        if categories:
            rows = [r for r in rows if r.get("category") in categories]
        if manufacturers:
            rows = [r for r in rows if r.get("manufacturer") in manufacturers]
        for key, wanted in (attributes or {}).items():
            rows = [r for r in rows if str(r.get(key, "")).lower() == str(wanted).lower()]
        booked = await self.booked_quantities(job_id) if job_id else {}
        items = [
            {
                **row,
                "available_qty": row.get("eventory_available_qty"),
                "booked_qty": booked.get(str(row.get("id")), 0),
                "booked": booked.get(str(row.get("id")), 0) > 0 if job_id else None,
            }
            for row in rows
        ]
        return {
            "items": items[skip : skip + limit],
            "total": len(items),
            "facets": facets,
            "availability": {"date_range_supported": False},
            "truncated": self.truncated,
        }

    async def list_cases(self) -> list[dict]:
        """Devices that contain other devices (Stockwire has no "is a case" flag).

        A device is a case when another device points at it through ``case_device_id``.
        """
        rows = await self._all_pages("/api/v1/inventory/devices", {})
        counts: dict[str, int] = {}
        for row in rows:
            if row.get("case_device_id"):
                key = str(row["case_device_id"])
                counts[key] = counts.get(key, 0) + 1
        cases = [r for r in rows if str(r.get("id")) in counts]
        products = await self._product_names(
            {str(r["product_id"]) for r in cases if r.get("product_id")}
        )
        names = {pid: body.get("name") for pid, body in products.items()}
        return [
            {
                "id": case["id"],
                "asset_tag": case.get("asset_tag"),
                "name": names.get(str(case.get("product_id"))) or case.get("asset_tag"),
                "child_count": counts[str(case["id"])],
            }
            for case in cases
        ]

    async def list_child_devices(self, case_device_id: int | str) -> list[dict]:
        """Devices inside a case/rack, each with its product summary.

        ``/inventory/devices`` ignores a ``case_device_id`` query parameter and returns every
        device, so the children are selected here by their ``case_device_id`` field.
        """
        rows = await self._all_pages("/api/v1/inventory/devices", {})
        children = [r for r in rows if str(r.get("case_device_id")) == str(case_device_id)]
        products = await self._product_names(
            {str(r["product_id"]) for r in children if r.get("product_id")}
        )
        return [
            {
                **child,
                "product": {
                    k: products[str(child.get("product_id"))].get(k)
                    for k in ("id", "name", "sku", "manufacturer", "category")
                }
                if str(child.get("product_id")) in products
                else None,
            }
            for child in children
        ]

    async def get_product(self, product_id: int | str) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get(f"/api/v1/inventory/products/{product_id}")
            response.raise_for_status()
            return response.json()

    async def list_category_tree(self) -> list[dict]:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.get("/api/v1/inventory/categories/tree")
            response.raise_for_status()
            return response.json()

    async def list_categories(self) -> list[dict]:
        tree = await self.list_category_tree()
        out: list[dict] = []

        def walk(nodes: list[dict], prefix: str) -> None:
            for node in nodes:
                name = node.get("name") or ""
                path = f"{prefix} > {name}" if prefix else name
                out.append({"id": node.get("id"), "path": path})
                children = node.get("children") or []
                if children:
                    walk(children, path)

        walk(tree, "")
        return out

    async def add_requirement(self, job_id: str, body: dict) -> dict:
        """Add one device to a stockwire-rental job (``POST /api/v1/jobs/{id}/requirements``)."""
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.post(f"/api/v1/jobs/{job_id}/requirements", json=body)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code} from stockwire-rental: {response.text[:300]}"
                )
            return response.json()

    async def update_requirement(self, requirement_id: int, body: dict) -> dict:
        """Change an existing requirement (e.g. its quantity)."""
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.put(f"/api/v1/jobs/requirements/{requirement_id}", json=body)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code} from stockwire-rental: {response.text[:300]}"
                )
            return response.json()

    async def delete_requirement(self, requirement_id: int) -> bool:
        """Remove a device requirement. Returns False if it was already gone (404)."""
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=15.0
        ) as client:
            response = await client.delete(f"/api/v1/jobs/requirements/{requirement_id}")
            if response.status_code == 404:
                return False
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code} from stockwire-rental: {response.text[:300]}"
                )
            return True

    async def request_additions(self, job_id: str, items: list[dict]) -> list[dict]:
        """Add each item as a requirement (one POST per item, as stockwire-rental expects)."""
        created: list[dict] = []
        for item in items:
            created.append(await self.add_requirement(job_id, item))
        return created
