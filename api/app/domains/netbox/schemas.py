"""Pydantic schemas for the NetBox integration API surface."""

from pydantic import BaseModel, Field


class NetboxIntegrationUpdate(BaseModel):
    """Admin-editable NetBox integration configuration."""

    enabled: bool = False
    base_url: str = ""
    api_token: str | None = None
    tenant_slug: str = ""
    site_slug: str = ""
    device_role_slug: str = "stagewire"
    # NetBox device_type is referenced by id; filled in by ``provision``.
    device_type_id: int | None = None
    default_device_status: str = "staged"
    # URL under which NetBox can reach this Stagewire API (for webhook callbacks).
    public_url: str = ""


class NetboxIntegrationOut(BaseModel):
    enabled: bool = False
    base_url: str = ""
    has_api_token: bool = False
    tenant_slug: str = ""
    site_slug: str = ""
    device_role_slug: str = "stagewire"
    device_type_id: int | None = None
    default_device_status: str = "staged"
    public_url: str = ""
    webhook_ready: bool = False


class NetboxTestResult(BaseModel):
    ok: bool = False
    status: int | None = None
    latency_ms: int | None = None
    detail: str = ""


class NetboxProvisionResult(BaseModel):
    ok: bool = False
    code: str = ""
    message: str = ""
    created: list[str] = Field(default_factory=list)


class NetboxAvailableIp(BaseModel):
    address: str
    family: int = 4


class NetboxAssignIpRequest(BaseModel):
    device_id: str
    # The prefix (CIDR) to draw an available address from; defaults to the
    # device's local ``network_subnet`` when omitted.
    prefix: str | None = None
    # When set, assign this exact address instead of drawing an available one.
    address: str | None = None
    description: str | None = None


class NetboxAssignIpResult(BaseModel):
    ok: bool = False
    ip: str | None = None
    netbox_ip_id: int | None = None
    message: str = ""


class NetboxSyncResult(BaseModel):
    ok: bool = False
    devices_created: int = 0
    devices_updated: int = 0
    message: str = ""
