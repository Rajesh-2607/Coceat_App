"""Primitives for passwords, session tokens and phone normalisation.

Raw passwords and tokens are never stored or logged."""

import base64
import hashlib
import hmac
import re
import secrets

from app.core.config import get_settings

SESSION_COOKIE = "cc_session"
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")

# scrypt cost parameters (OWASP-level). Stored with each hash so they can be raised later without breaking logins.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def _key() -> bytes:
    return get_settings().session_secret.get_secret_value().encode()


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 bound to a purpose so a hash from one context can't be replayed in another."""
    return hmac.new(_key(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return keyed_hash(token, "session")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, digest_b64 = stored.split("$")
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


# Checked when no account matches, so a wrong username takes as long as a wrong password.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def normalize_indian_mobile(raw: str) -> str | None:
    """Return E.164 (+91XXXXXXXXXX) or None if not a valid Indian mobile number."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _INDIAN_MOBILE.match(digits) else None
