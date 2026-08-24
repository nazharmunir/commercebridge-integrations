import base64
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app import main
from app.database import Database
from app.erp import ERPClient
from app.service import ConnectorService


def test_real_shopify_webhook_rejects_bad_hmac(monkeypatch):
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "secret")
    main.database = Database(":memory:")
    main.service = ConnectorService(main.database, ERPClient(sleep_fn=lambda _: None))
    client = TestClient(main.app)
    response = client.post(
        "/webhooks/shopify/orders/create",
        content=b'{"id":1}',
        headers={
            "X-Shopify-Hmac-Sha256": "bad",
            "X-Shopify-Webhook-Id": "wid-1",
            "X-Shopify-Shop-Domain": "store.myshopify.com",
        },
    )
    assert response.status_code == 401


def test_real_shopify_webhook_accepts_and_processes(monkeypatch):
    secret = "secret"
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", secret)
    main.database = Database(":memory:")
    main.service = ConnectorService(main.database, ERPClient(sleep_fn=lambda _: None))
    client = TestClient(main.app)
    payload = {
        "id": 991,
        "currency": "EUR",
        "customer": {"first_name": "Anna", "last_name": "Berg"},
        "line_items": [{"id": 1, "sku": "COSRX-SNL-100", "title": "Snail Essence", "quantity": 1, "price": "12.50"}],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    response = client.post(
        "/webhooks/shopify/orders/create",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Hmac-Sha256": signature,
            "X-Shopify-Webhook-Id": "wid-991",
            "X-Shopify-Shop-Domain": "store.myshopify.com",
            "X-Shopify-Topic": "orders/create",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    event = main.database.event_by_id(body["event_id"])
    assert event["status"] == "completed"
