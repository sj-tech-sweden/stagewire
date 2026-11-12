"""Verification of inbound NetBox webhook signatures.

NetBox computes an HMAC over the raw request body using the webhook's shared
secret and sends it in the ``X-Hook-Signature`` header. The default hash
algorithm is SHA-512; we accept SHA-512 and SHA-256 so the verifier also works
if an operator changes the webhook's algorithm away from the default.
"""

import hashlib
import hmac


def verify_netbox_signature(secret: str, raw_body: bytes, header_value: str | None) -> bool:
    """Return True when ``header_value`` is a valid HMAC of ``raw_body``.

    ``secret`` is the webhook secret configured on the NetBox webhook (stored
    encrypted in the integration config). The header is a hex digest.
    """
    if not secret or not header_value:
        return False
    expected_key = secret.encode("utf-8")
    candidates = [
        hmac.new(expected_key, raw_body, hashlib.sha512).hexdigest(),
        hmac.new(expected_key, raw_body, hashlib.sha256).hexdigest(),
    ]
    provided = header_value.strip().lower()
    return any(hmac.compare_digest(candidate, provided) for candidate in candidates)
