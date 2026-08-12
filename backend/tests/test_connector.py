from decimal import Decimal

from app.database import Database
from app.models import LineItem, ShopifyOrder
from app.service import ConnectorService


def order_with(sku: str, timeout: bool = False) -> ShopifyOrder:
    return ShopifyOrder(
        order_id="1049", customer_name="Han River Store",
        line_items=[LineItem(sku=sku, title="K-Beauty Product", quantity=2, unit_price=Decimal("24.90"))],
        simulate_erp_timeout=timeout,
    )


def test_valid_order_is_transformed_and_delivered():
    service = ConnectorService(Database(":memory:"))
    result = service.process_shopify_order(order_with("COSRX-SNL-100"), "shopify_1049")
    assert result.status == "completed"
    assert result.canonical_order.line_items[0].erp_sku == "ERP-COS-0100"


def test_duplicate_webhook_is_idempotent():
    service = ConnectorService(Database(":memory:"))
    service.process_shopify_order(order_with("COSRX-SNL-100"), "shopify_1049")
    duplicate = service.process_shopify_order(order_with("COSRX-SNL-100"), "shopify_1049")
    assert duplicate.status == "duplicate"


def test_unknown_sku_can_be_mapped_and_retried():
    database = Database(":memory:")
    service = ConnectorService(database)
    failed = service.process_shopify_order(order_with("ANUA-HRT-250-P"), "shopify_1050")
    assert failed.status == "needs_review"
    database.upsert_mapping("ANUA-HRT-250-P", "ERP-AN-0250", "Anua Heartleaf Toner 250ml")
    retried = service.retry(failed.event_id)
    assert retried.status == "completed"


def test_erp_timeout_preserves_retry_history():
    service = ConnectorService(Database(":memory:"))
    result = service.process_shopify_order(order_with("COSRX-SNL-100", timeout=True), "shopify_1051")
    assert result.status == "needs_review"
    assert result.attempts == 3
    assert "timed out" in result.error
