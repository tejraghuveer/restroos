from __future__ import annotations

import secrets
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: time-ordered, non-enumerable identifiers."""
    timestamp_ms = (time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(secrets.token_bytes(2), "big") & 0x0FFF
    rand_b = int.from_bytes(secrets.token_bytes(8), "big") & ((1 << 62) - 1)
    value = (timestamp_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def new_token(nbytes: int = 32) -> str:
    """URL-safe bearer secret (used for refresh tokens and invitations)."""
    return secrets.token_urlsafe(nbytes)
