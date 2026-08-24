import json
from uuid import uuid4

from .database import Database
from .erp import ERPClient, ERPDeliveryError
from .models import CanonicalLineItem, CanonicalOrder, EventResponse, ShopifyOrder


class ConnectorService:
    def __init__(self, database: Database, erp_client: ERPClient | None = None) -> None:
        self.db = database
        self.erp = erp_client or ERPClient()

    def enqueue_shopify_order(self, order: ShopifyOrder, idempotency_key: str, topic: str = "orders/create") -> EventResponse:
        existing = self.db.event_by_key(idempotency_key)
        if existing:
            return self._response(existing, override_status="duplicate")

        event_id = f"evt_{uuid4().hex[:12]}"
        self.db.create_event(
            event_id,
            idempotency_key,
            order.order_id,
            order.model_dump(mode="json"),
            shop_domain=order.shop_domain,
            topic=topic,
        )
        return self._response(self.db.event_by_id(event_id))

    def process_shopify_order(self, order: ShopifyOrder, idempotency_key: str) -> EventResponse:
        queued = self.enqueue_shopify_order(order, idempotency_key)
        if queued.status == "duplicate":
            return queued
        return self.process_event(queued.event_id)

    def retry(self, event_id: str) -> EventResponse:
        if not self.db.event_by_id(event_id):
            raise KeyError(event_id)
        return self.process_event(event_id)

    def process_event(self, event_id: str) -> EventResponse:
        event = self.db.event_by_id(event_id)
        if not event:
            raise KeyError(event_id)
        order = ShopifyOrder.model_validate(json.loads(event["payload"]))
        self.db.update_event(event_id, status="processing", attempts=event["attempts"])
        return self._process(event_id, order)

    def _process(self, event_id: str, order: ShopifyOrder) -> EventResponse:
        canonical_items = []
        missing = []

        for item in order.line_items:
            mapping = self.db.mapping_for(item.sku)
            if not mapping:
                missing.append(item.sku)
                continue
            canonical_items.append(
                CanonicalLineItem(
                    erp_sku=mapping["erp_sku"],
                    external_sku=item.sku,
                    description=mapping["product_name"],
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    vat_rate=item.vat_rate,
                )
            )

        if missing:
            error = f"Unknown SKU mapping: {', '.join(missing)}"
            self.db.update_event(event_id, status="needs_review", attempts=0, error=error)
            return self._response(self.db.event_by_id(event_id))

        canonical = CanonicalOrder(
            commerce_order_id=f"CB-{order.order_id}",
            source="shopify",
            source_order_id=order.order_id,
            customer_name=order.customer_name,
            currency=order.currency,
            line_items=canonical_items,
            shop_domain=order.shop_domain,
        )

        try:
            delivery = self.erp.deliver(canonical, simulate_timeout=order.simulate_erp_timeout)
        except ERPDeliveryError as exc:
            self.db.update_event(
                event_id,
                status="needs_review",
                attempts=exc.attempts,
                error=str(exc),
                canonical=canonical.model_dump(mode="json"),
            )
            return self._response(self.db.event_by_id(event_id))

        self.db.update_event(
            event_id,
            status="completed",
            attempts=delivery.attempts,
            canonical=canonical.model_dump(mode="json"),
            erp_reference=delivery.reference,
            processing_ms=delivery.processing_ms,
        )
        return self._response(self.db.event_by_id(event_id))

    def _response(self, row, override_status=None) -> EventResponse:
        canonical = json.loads(row["canonical_payload"]) if row["canonical_payload"] else None
        return EventResponse(
            event_id=row["event_id"],
            status=override_status or row["status"],
            source_order_id=row["source_order_id"],
            attempts=row["attempts"],
            error=row["error"],
            canonical_order=canonical,
            shop_domain=row["shop_domain"],
            webhook_id=row["idempotency_key"],
            erp_reference=row["erp_reference"],
            processing_ms=row["processing_ms"],
        )
