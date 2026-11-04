import base64
import datetime as dt
import hashlib
import hmac
import os
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jwt import PyJWTError

from app.core.config import settings

_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _aes_key() -> bytes:
    # Section 7.4 field-level encryption key. No row uses this yet
    # (complainant identity encryption is Phase 3, case_parties) — kept
    # here so the key-rotation job this phase builds has a real key.
    return base64.urlsafe_b64decode(settings.identifier_encryption_key)


def encrypt_field(plaintext: str) -> bytes:
    aesgcm = AESGCM(_aes_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_field(blob: bytes) -> str:
    aesgcm = AESGCM(_aes_key())
    nonce, ciphertext = blob[:12], blob[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def blind_index(value: str) -> str:
    """HMAC-SHA-256 blind index for searchable encrypted fields — never
    plain SHA-256 (a prior build's defect, see docs/decision-log.md)."""
    key = settings.identifier_fingerprint_key.encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    """Deliberately does NOT embed bureau/region assignments: those are
    looked up fresh from the DB on every request (core/deps.py) so a
    reassignment takes effect on the next request, not only after the
    access token expires (Section 4.2)."""
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def create_refresh_token(*, family_id: uuid.UUID, version: int) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "family": str(family_id),
        "version": version,
        "iat": now,
        "exp": now + dt.timedelta(days=settings.refresh_token_ttl_days),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def create_step_up_token(*, user_id: uuid.UUID) -> str:
    """Section 4.1 step-up re-authentication: a short-lived claim proving
    TOTP (or, on mobile, biometric) was freshly re-verified, required by
    sensitive endpoints (transfer, escalation, disposal, confidential
    export, role change — enforced as those features are built)."""
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.step_up_ttl_minutes),
        "type": "step_up",
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
    except PyJWTError as exc:
        raise ValueError("invalid token") from exc


def generate_csrf_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def verify_csrf_token(token_a: str, token_b: str) -> bool:
    """Constant-time comparison for CSRF tokens to prevent timing attacks."""
    if not token_a or not token_b:
        return False
    return hmac.compare_digest(token_a.encode("utf-8"), token_b.encode("utf-8"))

