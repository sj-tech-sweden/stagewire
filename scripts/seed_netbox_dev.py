#!/usr/bin/env python3
"""Seed a local dev NetBox with the objects the Stagewire integration expects.

This is a dev-only convenience script. It is idempotent: objects that already
exist (by slug) are left alone. It creates:

  * a tenant (default: ``stagewire``)
  * a site   (default: ``hq``)
  * a device role ``stagewire``
  * a manufacturer ``Generic`` and device type ``Generic / Stagewire Device``
  * an API token for Stagewire to authenticate with (printed at the end)

It talks to the NetBox REST API over HTTP using the superuser credentials you
pass on the command line, provisions a token via NetBox's token-provision
endpoint, and prints the token so you can paste it into the Stagewire Settings →
NetBox tab.

Usage:
    python scripts/seed_netbox_dev.py \\
        --base-url http://localhost:8000 \\
        --user admin --password admin \\
        --site hq --tenant stagewire

Dependencies: Python 3.9+ standard library only (no third-party packages).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _request(
    base_url: str,
    token: str | None,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    basic: tuple[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    if basic:
        import base64

        raw = f"{basic[0]}:{basic[1]}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (dev script)
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:  # NetBox returns errors as HTTPError
        payload = exc.read().decode() or "{}"
        try:
            detail = json.loads(payload)
        except ValueError:
            detail = {"detail": payload[:300]}
        return exc.code, detail


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def ensure_object(
    base_url: str,
    token: str,
    list_path: str,
    create_path: str,
    lookup_field: str,
    value: str,
    create_body: dict[str, Any],
) -> dict[str, Any]:
    """Idempotently create a NetBox object, returning the existing/created row."""
    status, listing = _request(base_url, token, "GET", f"{list_path}?{lookup_field}={value}")
    results = listing.get("results", []) if isinstance(listing, dict) else []
    if results:
        print(f"  exists: {create_path} {value} (id={results[0]['id']})")
        return results[0]
    status, created = _request(base_url, token, "POST", create_path, body=create_body)
    if status >= 400:
        raise SystemExit(f"Failed to create {create_path} {value}: HTTP {status} {created}")
    print(f"  created: {create_path} {value} (id={created.get('id')})")
    return created


def get_token(base_url: str, user: str, password: str) -> str:
    """Provision an API token using the superuser's basic auth.

    NetBox exposes ``/api/users/tokens/provision/`` which, when called with valid
    credentials, returns a freshly provisioned token key.
    """
    status, body = _request(
        base_url,
        None,
        "POST",
        "/api/users/tokens/provision/",
        body={"description": "stagewire-integration-dev"},
        basic=(user, password),
    )
    if status >= 400 or "key" not in body:
        raise SystemExit(
            f"Could not provision a NetBox token (HTTP {status}): {body}. "
            "Check the superuser credentials and that NetBox is up."
        )
    return body["key"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a dev NetBox for Stagewire.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--site", default="hq", help="Site slug to create.")
    parser.add_argument("--tenant", default="stagewire", help="Tenant slug to create.")
    parser.add_argument("--role", default="stagewire", help="Device role slug to create.")
    parser.add_argument("--manufacturer", default="Generic")
    parser.add_argument("--device-model", default="Stagewire Device")
    args = parser.parse_args()

    print(f"Seeding NetBox at {args.base_url} ...")
    token = get_token(args.base_url, args.user, args.password)
    print(f"  token provisioned (key hidden)")

    # Tenant
    ensure_object(
        args.base_url,
        token,
        "/api/tenancy/tenants/",
        "/api/tenancy/tenants/",
        "slug",
        _slug(args.tenant),
        {"name": args.tenant, "slug": _slug(args.tenant)},
    )

    # Site (requires no other FKs in NetBox)
    ensure_object(
        args.base_url,
        token,
        "/api/dcim/sites/",
        "/api/dcim/sites/",
        "slug",
        _slug(args.site),
        {"name": args.site, "slug": _slug(args.site)},
    )

    # Device role
    ensure_object(
        args.base_url,
        token,
        "/api/dcim/device-roles/",
        "/api/dcim/device-roles/",
        "slug",
        _slug(args.role),
        {"name": args.role, "slug": _slug(args.role), "color": "teal"},
    )

    # Manufacturer
    man = ensure_object(
        args.base_url,
        token,
        "/api/dcim/manufacturers/",
        "/api/dcim/manufacturers/",
        "slug",
        _slug(args.manufacturer),
        {"name": args.manufacturer, "slug": _slug(args.manufacturer)},
    )

    # Device type (needs the manufacturer id)
    ensure_object(
        args.base_url,
        token,
        "/api/dcim/device-types/",
        "/api/dcim/device-types/",
        "model",
        args.device_model,
        {
            "manufacturer": man["id"],
            "model": args.device_model,
            "slug": _slug(args.device_model),
        },
    )

    print("\nDone. Paste these into Stagewire Settings → NetBox:")
    print(f"  Base URL:        {args.base_url}")
    print(f"  Tenant slug:     {_slug(args.tenant)}")
    print(f"  Site slug:       {_slug(args.site)}")
    print(f"  Device role:     {_slug(args.role)}")
    print(f"  API token:       {token}")
    print("\nPublic URL (so NetBox webhooks reach Stagewire):")
    print("  http://host.docker.internal:8010  (from inside Docker)")
    print("  http://localhost:8010             (when Stagewire runs on the host)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
