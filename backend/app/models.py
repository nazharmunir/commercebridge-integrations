from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    sku: str = Field(min_length=1)
    title: str
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(default=Decimal("0.19"), ge=0)


class ShopifyOrder(BaseModel):
    order_id: str
    customer_name: str
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    line_items: list[LineItem] = Field(min_length=1)
    shop_domain: str | None = None
    created_at: datetime | None = None
    simulate_erp_timeout: bool = False


class MappingRequest(BaseModel):
    external_sku: str
    erp_sku: str
    product_name: str


class CanonicalLineItem(BaseModel):
    erp_sku: str
    external_sku: str
    description: str
    quantity: int
    unit_price: Decimal
    vat_rate: Decimal


class CanonicalOrder(BaseModel):
    commerce_order_id: str
    source: str
    source_order_id: str
    customer_name: str
    currency: str
    line_items: list[CanonicalLineItem]
    shop_domain: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventResponse(BaseModel):
    event_id: str
    status: Literal["queued", "processing", "completed", "needs_review", "duplicate"]
    source_order_id: str
    attempts: int
    error: str | None = None
    canonical_order: CanonicalOrder | None = None
    shop_domain: str | None = None
    webhook_id: str | None = None
    erp_reference: str | None = None
    processing_ms: int | None = None


class WebhookAck(BaseModel):
    accepted: bool
    duplicate: bool = False
    event_id: str
    webhook_id: str
    status: str


class ReconciliationResult(BaseModel):
    checked: int
    missing: int
    queued: int
    duplicates: int
    event_ids: list[str]
