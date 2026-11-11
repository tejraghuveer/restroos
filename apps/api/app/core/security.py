from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.enums import Role
from app.core.ids import uuid7

ACCESS_AUDIENCE = "restroos:app"


class TokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
    restaurant_id: uuid.UUID | None
    role: Role
    jti: str


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    restaurant_id: uuid.UUID | None,
    role: Role,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "aud": ACCESS_AUDIENCE,
        "iss": settings.jwt_issuer,
        "typ": "access",
        "jti": uuid7().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "tenant_id": str(tenant_id),
        "membership_id": str(membership_id),
        "restaurant_id": str(restaurant_id) if restaurant_id else None,
        "role": role.value,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=ACCESS_AUDIENCE,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "aud", "iss", "exp", "iat", "jti", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid access token") from exc

    if payload.get("typ") != "access":
        raise TokenError("Invalid token type")

    try:
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            membership_id=uuid.UUID(payload["membership_id"]),
            restaurant_id=(
                uuid.UUID(payload["restaurant_id"]) if payload.get("restaurant_id") else None
            ),
            role=Role(payload["role"]),
            jti=payload["jti"],
        )
    except (KeyError, ValueError) as exc:
        raise TokenError("Invalid token claims") from exc
