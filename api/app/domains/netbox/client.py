"""Thin async client for the NetBox REST API (v3.7+ / v4.x).

NetBox 4.7 authenticates API tokens with ``Authorization: Bearer nbt_<key>.<token>``
(a version-2 token, where ``key`` is the short display key — prefixed with
``nbt_`` — and ``token`` is the secret). The legacy ``Token <token>`` (v1) scheme
is rejected for v2 tokens. The token stored in settings is therefore the full
``Bearer nbt_<key>.<token>`` string emitted by the seed script; if a bare value
is supplied the client prefixes the ``Bearer `` scheme (assuming a
``nbt_<key>.<token>`` secret was pasted without it).

The client is deliberately close to ``StockwireClient`` so the two integration
domains read the same way, but it speaks NetBox's own shapes: list endpoints
return ``{count, next, previous, results}`` and write endpoints for devices need
a real ``device_type`` (referenced by id) plus ``role``/``site`` (referenced by
slug).
"""

import time

import httpx

from app.core.config import get_settings
from app.domains.netbox.config import (
    NETBOX_CF_CONTENT_TYPES,
    NETBOX_CF_DEVICE_ID,
    NETBOX_CF_JOB_ID,
    NETBOX_CF_LINK,
    NETBOX_CF_SYNC_STATUS,
    NETBOX_WEBHOOK_CONTENT_TYPES,
)

CACHE_TTL_SECONDS = 60.0
_PAGE_CACHE: dict[tuple, tuple[float, list[dict]]] = {}


class NetboxClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._transport = transport
        settings = get_settings()
        self.base_url = (base_url or settings.netbox_api_base_url).rstrip("/")
        self.token = token or settings.netbox_api_token

    def _headers(self) -> dict[str, str]:
        # NetBox 4.7 uses version-2 tokens: the Authorization header must be
        # `Bearer nbt_<key>.<token>`. The settings value is normally the full
        # `Bearer ...` string the seed script prints, so use it verbatim when it
        # already carries a scheme; otherwise prefix `Bearer ` (a bare
        # `nbt_<key>.<token>` secret was pasted without the scheme). Never send
        # the legacy `Token <token>` form, which NetBox 4.7 rejects for v2 tokens.
        token = self.token or ""
        if token.lower().startswith(("bearer ", "token ")):
            auth = token
        else:
            auth = f"Bearer {token}"
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": auth,
        }

    def _client(self, timeout: float = 15.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
            transport=self._transport,
        )

    async def _request(
        self, method: str, path: str, *, params: dict | None = None, json: dict | None = None
    ) -> dict | list:
        async with self._client() as client:
            response = await client.request(method, path, params=params, json=json)
            self._raise_for_status(method, path, response)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    @staticmethod
    def _raise_for_status(method: str, path: str, response: httpx.Response) -> None:
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str(body.get("detail") or body)
            except ValueError:
                detail = response.text[:300]
            raise RuntimeError(
                f"NetBox {method} {path} failed: HTTP {response.status_code} — {detail}"
            )

    async def _results(self, path: str, params: dict | None = None) -> list[dict]:
        """Collect every page of a NetBox list endpoint into a flat list."""
        key = (self.base_url, hash(self.token), path, tuple(sorted((params or {}).items())))
        cached = _PAGE_CACHE.get(key) if self._transport is None else None
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        rows: list[dict] = []
        params = dict(params or {})
        params.setdefault("limit", 100)
        url = path
        async with self._client() as client:
            while url is not None:
                # The first call uses the given path + params; subsequent calls
                # use NetBox' absolute ``next`` URL when present.
                if url == path:
                    resp = await client.get(url, params=params)
                else:
                    resp = await client.get(url)
                self._raise_for_status("GET", url, resp)
                body = resp.json()
                page = body.get("results", []) if isinstance(body, dict) else body
                rows.extend(page)
                url = body.get("next") if isinstance(body, dict) else None
        if self._transport is None:
            _PAGE_CACHE[key] = (time.monotonic(), rows)
        return rows

    # --- Provisioning -------------------------------------------------------

    async def ensure_custom_fields(self) -> list[str]:
        """Create Stagewire's custom fields idempotently. Returns created keys."""
        defined = [
            (NETBOX_CF_JOB_ID, "text", "Stagewire production job ID"),
            (NETBOX_CF_DEVICE_ID, "text", "Stagewire graph device ID"),
            (NETBOX_CF_SYNC_STATUS, "text", "Stagewire sync status (ok/conflict/error)"),
            (NETBOX_CF_LINK, "url", "Link back to the Stagewire job/device view"),
        ]
        created: list[str] = []
        for key, ftype, description in defined:
            existing = await self._results("/api/extras/custom-fields/", params={"key": key})
            if existing:
                continue
            await self._request(
                "POST",
                "/api/extras/custom-fields/",
                json={
                    "key": key,
                    "label": f"Stagewire {key}",
                    "type": ftype,
                    "content_types": NETBOX_CF_CONTENT_TYPES,
                    "description": description,
                },
            )
            created.append(key)
        return created

    async def ensure_webhook(self, name: str, callback_url: str, secret: str) -> bool:
        """Create the Stagewire sync webhook if missing. Returns True if created."""
        existing = await self._results("/api/extras/webhooks/", params={"name": name})
        if existing:
            return False
        await self._request(
            "POST",
            "/api/extras/webhooks/",
            json={
                "name": name,
                "content_types": NETBOX_WEBHOOK_CONTENT_TYPES,
                "type_create": True,
                "type_update": True,
                "type_delete": True,
                "payload_url": callback_url,
                "http_method": "POST",
                "secret": secret,
                # Local dev callback is plain http; never verify TLS there.
                "ssl_verification": False,
                "enabled": True,
            },
        )
        return True

    async def ensure_device_role(self, slug: str, name: str) -> int:
        """Return the id of the device role with ``slug`` (creating it if needed)."""
        existing = await self._results("/api/dcim/device-roles/", params={"slug": slug})
        if existing:
            return int(existing[0]["id"])
        created = await self._request(
            "POST",
            "/api/dcim/device-roles/",
            json={"name": name, "slug": slug, "color": "teal"},
        )
        return int(created["id"])

    async def ensure_device_type(self, model: str, manufacturer: str) -> int:
        """Return the id of a device type, creating the manufacturer + type."""
        man = await self._results(
            "/api/dcim/manufacturers/", params={"slug": manufacturer.lower().replace(" ", "-")}
        )
        if man:
            man_id = int(man[0]["id"])
        else:
            made = await self._request(
                "POST",
                "/api/dcim/manufacturers/",
                json={
                    "name": manufacturer,
                    "slug": manufacturer.lower().replace(" ", "-"),
                },
            )
            man_id = int(made["id"])
        existing = await self._results(
            "/api/dcim/device-types/",
            params={"model": model, "manufacturer_id": man_id},
        )
        if existing:
            return int(existing[0]["id"])
        created = await self._request(
            "POST",
            "/api/dcim/device-types/",
            json={"manufacturer": man_id, "model": model, "slug": model.lower().replace(" ", "-")},
        )
        return int(created["id"])

    # --- Devices ------------------------------------------------------------

    async def find_device(self, stagewire_device_id: str) -> dict | None:
        rows = await self._results(
            "/api/dcim/devices/", params={f"cf_{NETBOX_CF_DEVICE_ID}": stagewire_device_id}
        )
        return rows[0] if rows else None

    async def create_device(
        self,
        *,
        name: str,
        site_slug: str,
        device_type_id: int,
        role_slug: str,
        status_slug: str,
        tenant_slug: str | None,
        custom_fields: dict,
    ) -> dict:
        body: dict = {
            "name": name,
            "device_type": device_type_id,
            "role": {"slug": role_slug},
            "site": {"slug": site_slug},
            "status": status_slug,
            "custom_fields": custom_fields,
        }
        if tenant_slug:
            body["tenant"] = {"slug": tenant_slug}
        return await self._request("POST", "/api/dcim/devices/", json=body)

    async def update_device(self, netbox_id: int, patch: dict) -> dict:
        return await self._request("PATCH", f"/api/dcim/devices/{netbox_id}/", json=patch)

    # --- IPAM ---------------------------------------------------------------

    async def find_prefix(self, cidr: str) -> dict | None:
        rows = await self._results("/api/ipam/prefixes/", params={"prefix": cidr})
        return rows[0] if rows else None

    async def available_ips(self, prefix_id: int) -> list[dict]:
        # ``available-ips`` is a GET that returns available addresses (no ids yet).
        return await self._results(f"/api/ipam/prefixes/{prefix_id}/available-ips/")

    async def create_ip(
        self,
        *,
        address: str,
        device_id: int,
        custom_fields: dict,
        description: str | None = None,
        status: str = "active",
    ) -> dict:
        body: dict = {
            "address": address,
            "status": status,
            "assigned_object_type": "dcim.device",
            "assigned_object_id": device_id,
            "custom_fields": custom_fields,
        }
        if description:
            body["description"] = description
        return await self._request("POST", "/api/ipam/ip-addresses/", json=body)

    async def get_ip(self, ip_id: int) -> dict:
        return await self._request("GET", f"/api/ipam/ip-addresses/{ip_id}/")

    async def delete_ip(self, ip_id: int) -> None:
        async with self._client() as client:
            response = await client.request("DELETE", f"/api/ipam/ip-addresses/{ip_id}/")
            self._raise_for_status("DELETE", f"/api/ipam/ip-addresses/{ip_id}/", response)
