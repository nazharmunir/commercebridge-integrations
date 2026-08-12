import json
from uuid import uuid4

from .database import Database
from .models import CanonicalLineItem, CanonicalOrder, EventResponse, ShopifyOrder


class ConnectorService:
    def __init__(self, database: Database) -> None:
        self.db = database

    def process_shopify_order(self, order: ShopifyOrder, idempotency_key: str) -> EventResponse:
        existing = self.db.event_by_key(idempotency_key)
        if existing:
            return self._response(existing, override_status="duplicate")

        event_id = f"evt_{uuid4().hex[:12]}"
        self.db.create_event(event_id, idempotency_key, order.order_id, order.model_dump(mode="json"))
        return self._process(event_id, order)

    def retry(self, event_id: str) -> EventResponse:
        event = self.db.event_by_id(event_id)
        if not event:
            raise KeyError(event_id)
        order = ShopifyOrder.model_validate(json.loads(event["payload"]))
        return self._process(event_id, order)

    def _process(self, event_id: str, order: ShopifyOrder) -> EventResponse:
        event = self.db.event_by_id(event_id)
        attempts = int(event["attempts"]) + 1
        canonical_items = []
        missing = []

        for item in order.line_items:
            mapping = self.db.mapping_for(item.sku)
            if not mapping:
                missing.append(item.sku)
                continue
            canonical_items.append(
                CanonicalLineItem(
                    erp_sku=mapping["erp_sku"], external_sku=item.sku,
                    description=mapping["product_name"], quantity=item.quantity,
                    unit_price=item.unit_price, vat_rate=item.vat_rate,
                )
            )

        if missing:
            error = f"Unknown SKU mapping: {', '.join(missing)}"
            self.db.update_event(event_id, status="needs_review", attempts=attempts, error=error)
            return self._response(self.db.event_by_id(event_id))

        canonical = CanonicalOrder(
            commerce_order_id=f"CB-{order.order_id}", source="shopify",
            source_order_id=order.order_id, customer_name=order.customer_name,
            currency=order.currency, line_items=canonical_items,
        )

        if order.simulate_erp_timeout:
            error = "ERP gateway timed out after 3 delivery attempts"
            self.db.update_event(event_id, status="needs_review", attempts=3, error=error, canonical=canonical.model_dump(mode="json"))
            return self._response(self.db.event_by_id(event_id))

        self.db.update_event(event_id, status="completed", attempts=attempts, canonical=canonical.model_dump(mode="json"))
        return self._response(self.db.event_by_id(event_id))

    def _response(self, row, override_status=None) -> EventResponse:
        canonical = json.loads(row["canonical_payload"]) if row["canonical_payload"] else None
        return EventResponse(
            event_id=row["event_id"], status=override_status or row["status"],
            source_order_id=row["source_order_id"], attempts=row["attempts"],
            error=row["error"], canonical_order=canonical,
        )
