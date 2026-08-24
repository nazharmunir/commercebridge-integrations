import base64
import hashlib
import hmac
from decimal import Decimal

from app.database import Database
from app.erp import ERPClient
from app.models import LineItem, ShopifyOrder
from app.service import ConnectorService
from app.shopify import order_from_webhook, verify_shopify_hmac


def service_with_memory_db() -> ConnectorService:
    return ConnectorService(Database(":memory:"), ERPClient(sleep_fn=lambda _: None))


def order_with(sku: str, timeout: bool = False) -> ShopifyOrder:
    return ShopifyOrder(
        order_id="1049",
        customer_name="Han River Store",
        line_items=[LineItem(sku=sku, title="K-Beauty Product", quantity=2, unit_price=Decimal("24.90"))],
        simulate_erp_timeout=timeout,
    )


def test_valid_order_is_transformed_and_delivered():
    result = service_with_memory_db().process_shopify_order(order_with("COSRX-SNL-100"), "webhook-1049")
    assert result.status == "completed"
    assert result.canonical_order.line_items[0].erp_sku == "ERP-COS-0100"
    assert result.erp_reference.startswith("ERP-")


def test_duplicate_webhook_is_idempotent():
    service = service_with_memory_db()
    service.process_shopify_order(order_with("COSRX-SNL-100"), "webhook-1049")
    duplicate = service.process_shopify_order(order_with("COSRX-SNL-100"), "webhook-1049")
    assert duplicate.status == "duplicate"


def test_unknown_sku_can_be_mapped_and_retried():
    database = Database(":memory:")
    service = ConnectorService(database, ERPClient(sleep_fn=lambda _: None))
    failed = service.process_shopify_order(order_with("ANUA-HRT-250-P"), "webhook-1050")
    assert failed.status == "needs_review"
    database.upsert_mapping("ANUA-HRT-250-P", "ERP-AN-0250", "Anua Heartleaf Toner 250ml")
    retried = service.retry(failed.event_id)
    assert retried.status == "completed"


def test_erp_timeout_preserves_retry_history():
    result = service_with_memory_db().process_shopify_order(order_with("COSRX-SNL-100", timeout=True), "webhook-1051")
    assert result.status == "needs_review"
    assert result.attempts == 3
    assert "3 delivery attempts" in result.error


def test_shopify_hmac_verification_uses_raw_body():
    raw = b'{"id":123}'
    secret = "top-secret"
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    assert verify_shopify_hmac(raw, signature, secret)
    assert not verify_shopify_hmac(raw + b" ", signature, secret)


def test_shopify_webhook_is_normalized():
    order = order_from_webhook(
        {
            "id": 12345,
            "currency": "EUR",
            "customer": {"first_name": "Anna", "last_name": "Berg"},
            "line_items": [{"id": 1, "sku": "COSRX-SNL-100", "title": "Snail Essence", "quantity": 2, "price": "12.50"}],
        },
        "demo-store.myshopify.com",
    )
    assert order.order_id == "12345"
    assert order.customer_name == "Anna Berg"
    assert order.shop_domain == "demo-store.myshopify.com"
    assert order.line_items[0].unit_price == Decimal("12.50")


def test_enqueue_then_process_models_async_webhook_flow():
    service = service_with_memory_db()
    queued = service.enqueue_shopify_order(order_with("COSRX-SNL-100"), "shopify-webhook-id-1")
    assert queued.status == "queued"
    completed = service.process_event(queued.event_id)
    assert completed.status == "completed"
