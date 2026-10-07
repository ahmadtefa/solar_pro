"""Security primitives: password hashing, JWT issuing/validation, token storage.

Design notes
------------
* Passwords are hashed with bcrypt.  A SHA-256 pre-hash is applied first so the
  72 byte bcrypt limit cannot be used to silently truncate long passwords.
* Access tokens are short lived JWTs carrying the tenant (``cid``), the session
  (``sid``) and a password fingerprint (``pwdv``) so that changing a password
  or revoking a session immediately invalidates previously issued tokens.
* Refresh tokens are opaque random strings; only their SHA-256 digest is stored
  in the database, so a database leak cannot be replayed against the API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError, ValidationFailure

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

_PASSWORD_RULES = (
    (re.compile(r"[A-Z]"), "an uppercase letter"),
    (re.compile(r"[a-z]"), "a lowercase letter"),
    (re.compile(r"\d"), "a digit"),
)


def _prehash(password: str) -> bytes:
    """SHA-256 -> base64 keeps every password inside bcrypt's 72 byte window."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """Hash a plain password with bcrypt."""
    validate_password_policy(password)
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(_prehash(password), salt).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time password verification."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_policy(password: str) -> None:
    """Enforce the configured password policy, raising a 422 on failure."""
    problems: list[str] = []
    if len(password or "") < settings.password_min_length:
        problems.append(f"be at least {settings.password_min_length} characters long")
    for pattern, label in _PASSWORD_RULES:
        if not pattern.search(password or ""):
            problems.append(f"contain {label}")
    if problems:
        raise ValidationFailure("Password must " + ", ".join(problems), fields=["password"])


def password_fingerprint(password_hash: str) -> str:
    """Short deterministic fingerprint embedded in access tokens."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_access_token(
    *,
    user_id: uuid.UUID | str,
    company_id: uuid.UUID | str | None,
    session_id: uuid.UUID | str | None,
    password_hash: str,
    permissions_version: int = 0,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Return ``(token, expires_at)`` for the given identity."""
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "cid": str(company_id) if company_id else None,
        "sid": str(session_id) if session_id else None,
        "typ": ACCESS_TOKEN_TYPE,
        "jti": uuid.uuid4().hex,
        "pwdv": password_fingerprint(password_hash),
        "pv": permissions_version,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.app_name,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_token(token: str, *, expected_type: str = ACCESS_TOKEN_TYPE) -> dict[str, Any]:
    """Decode and validate a JWT, raising ``AuthenticationError`` when invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired", reason="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid", reason="token_invalid") from exc
    if payload.get("typ") != expected_type:
        raise AuthenticationError("Unexpected token type", reason="token_type_mismatch")
    return payload


def generate_opaque_token(nbytes: int = 48) -> str:
    """URL safe random token for refresh / reset flows."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Deterministic digest used to persist opaque tokens."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)


def password_reset_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.password_reset_expire_minutes)


def generate_temporary_password(length: int = 12) -> str:
    """Generate a temporary password that satisfies the policy."""
    alphabet = "abcdefghijkmnopqrstuvwxyz"
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digits = "23456789"
    symbols = "@#$%&*!"
    core = [
        secrets.choice(upper),
        secrets.choice(alphabet),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    pool = alphabet + upper + digits + symbols
    core.extend(secrets.choice(pool) for _ in range(max(length, 12) - len(core)))
    secrets.SystemRandom().shuffle(core)
    return "".join(core)


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)
