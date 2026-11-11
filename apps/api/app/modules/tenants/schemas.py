from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.core.enums import RestaurantStatus, TenantStatus


def _valid_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown IANA timezone") from exc
    return value


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: TenantStatus
    currency: str
    timezone: str
    created_at: datetime


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    timezone: str | None = Field(default=None, max_length=64)
    currency: Literal["INR"] | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _valid_timezone(value)


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=16)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    tax_inclusive: bool = False
    service_charge_bp: int = Field(default=0, ge=0, le=5000)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        result = _valid_timezone(value)
        assert result is not None
        return result


class RestaurantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: RestaurantStatus
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str
    timezone: str
    currency: str
    gstin: str | None
    tax_inclusive: bool
    service_charge_bp: int
    created_at: datetime


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    price_cents: int
    currency: str
    limits: dict
    current_period_start: datetime
    current_period_end: datetime | None
