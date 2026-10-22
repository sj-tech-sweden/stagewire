from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

VALID_ROLES = {"admin", "manager", "viewer"}


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str = ""
    last_name: str = ""
    full_name: str
    is_active: bool
    role: str
    notification_channel: str | None = None
    auth_source: str
    external_provider: str | None = None
    preferred_language: str = "en"
    created_at: datetime


class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    is_active: bool = True
    role: Literal["admin", "manager", "viewer"] = "viewer"
    notification_channel: str = "both"
    preferred_language: str = "en"


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    role: Literal["admin", "manager", "viewer"] | None = None
    notification_channel: str | None = None
    preferred_language: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserSelfUpdate(BaseModel):
    email: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    password: str | None = None
    notification_channel: str = "both"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummary
    refresh_token: str | None = None


class SSOProviderSummary(BaseModel):
    provider: str
    kind: Literal["oidc", "saml"]
    display_name: str
    enabled: bool
    auto_create_users: bool


class OIDCProviderConfig(BaseModel):
    key: str
    display_name: str = ""
    enabled: bool = True
    issuer: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: str = "openid email profile"
    group_claim: str = "groups"
    email_claim: str = "email"
    name_claim: str = "name"
    subject_claim: str = "sub"
    allow_auto_create: bool = False


class SAMLProviderConfig(BaseModel):
    key: str
    display_name: str = ""
    enabled: bool = True
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_x509_cert: str = ""
    sp_entity_id: str = ""
    acs_url: str = ""
    group_attribute: str = "groups"
    email_attribute: str = "email"
    name_attribute: str = "name"
    subject_attribute: str = "nameID"
    allow_auto_create: bool = False


class SSOConfig(BaseModel):
    enabled: bool = False
    auto_create_users: bool = False
    sync_roles_on_login: bool = False
    default_role: str = "viewer"
    group_role_map: dict[str, str] = {}
    oidc_providers: list[OIDCProviderConfig] = []
    saml_providers: list[SAMLProviderConfig] = []


class OIDCExchangeRequest(BaseModel):
    provider: str
    code: str
    redirect_uri: str
    state: str | None = None


class SAMLAssertionRequest(BaseModel):
    provider: str
    saml_response: str


class SAMLACSRequest(BaseModel):
    provider: str
    saml_response: str
    relay_state: str = ""


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RoleCreate(BaseModel):
    name: str
    display_name: str | None = None
    permissions: list[str] | None = None


class RoleAssign(BaseModel):
    role_id: int


class APIKeyCreate(BaseModel):
    name: str
    is_admin: bool = False
    raw_key: str


class APIKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_admin: bool
    created_at: datetime
