"""Primitives for OTPs, session tokens and hashing. Raw OTPs and tokens are never stored or logged."""

import hashlib
import hmac
import re
import secrets

from app.core.config import get_settings

DEV_OTP = "123456"
SESSION_COOKIE = "cc_session"
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")


def _key() -> bytes:
    return get_settings().session_secret.get_secret_value().encode()


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 bound to a purpose so a hash from one context can't be replayed in another."""
    return hmac.new(_key(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return keyed_hash(token, "session")


def new_otp() -> str:
    if get_settings().otp_dev_mode:
        return DEV_OTP
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(challenge_id: str, code: str) -> str:
    return keyed_hash(f"{challenge_id}:{code}", "otp")


def otp_matches(challenge_id: str, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(challenge_id, code), expected_hash)


def hash_ip(ip: str | None) -> str | None:
    return keyed_hash(ip, "ip") if ip else None


def normalize_indian_mobile(raw: str) -> str | None:
    """Return E.164 (+91XXXXXXXXXX) or None if not a valid Indian mobile number."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _INDIAN_MOBILE.match(digits) else None
