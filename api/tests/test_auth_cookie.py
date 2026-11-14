"""Regression coverage for the httpOnly refresh-token cookie behaviour.

The cookie must be usable in non-production (dev/test, plain http) environments,
where ``secure_cookies`` is False. ``SameSite=None`` mandates ``Secure``, so a
None+insecure cookie is silently dropped by browsers — which used to break the
refresh flow (and the e2e recovery test) outside of production.
"""

from fastapi import Response

from app.core.config import get_settings
from app.domains.auth.router import _refresh_cookie_samesite, _set_refresh_cookie


def test_refresh_cookie_samesite_is_lax_when_insecure() -> None:
    # APP_ENV=test (conftest) => secure_cookies is False.
    settings = get_settings()
    assert settings.secure_cookies is False
    assert _refresh_cookie_samesite() == "lax"


def test_refresh_cookie_samesite_is_none_when_secure() -> None:
    settings = get_settings()
    original = settings.app_env
    try:
        settings.app_env = "production"
        assert settings.secure_cookies is True
        assert _refresh_cookie_samesite() == "none"
    finally:
        settings.app_env = original


def test_set_refresh_cookie_writes_lax_samesite_in_test_env() -> None:
    response = Response()
    _set_refresh_cookie(response, "test-refresh-token")
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=test-refresh-token" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # Must never advertise SameSite=None without Secure in a non-prod context.
    assert "samesite=none" not in set_cookie.lower()