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


class StockwireClient:
    """Thin async client for the Stockwire Rental API."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
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
