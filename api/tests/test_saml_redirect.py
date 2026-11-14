"""Regression coverage for the SAML redirect/ACS round-trip.

Before the fix, ``build_saml_redirect_url`` called ``saml.to_settings()``, which
does not exist (AttributeError) and passed no RelayState, so ``saml_acs`` rejected
the response as "Invalid SAML relay state". The SAML login flow never worked.
"""

from urllib.parse import parse_qs, urlparse

from app.domains.auth.sso import SAMLProvider, build_saml_redirect_url
from app.domains.auth.router import _decode_saml_relay_state


def _make_provider(key: str = "test-provider") -> SAMLProvider:
    return SAMLProvider(
        key=key,
        display_name="Test IdP",
        idp_entity_id="https://idp.example.com/entity",
        idp_sso_url="https://idp.example.com/sso",
        idp_x509_cert="",
        sp_entity_id="https://sp.example.com",
        acs_url="https://sp.example.com/api/v1/auth/sso/saml/acs",
        group_attribute="groups",
        email_attribute="email",
        name_attribute="name",
        subject_attribute="nameID",
        allow_auto_create=False,
        enabled=True,
    )


def test_build_saml_redirect_url_embeds_relay_state() -> None:
    provider = _make_provider()
    url = build_saml_redirect_url(provider)
    assert isinstance(url, str) and url
    assert "RelayState" in url
    qs = parse_qs(urlparse(url).query)
    assert "RelayState" in qs, f"RelayState missing from {url}"
    decoded = _decode_saml_relay_state(qs["RelayState"][0])
    assert decoded.get("provider") == provider.key
    assert decoded.get("redirect") == "/"
