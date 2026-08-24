from decimal import Decimal

from app.shopify import ShopifyAdminClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_client_credentials_are_used_and_cached(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"access_token": "token-123", "expires_in": 86399})

    monkeypatch.setattr("app.shopify.httpx.post", fake_post)
    client = ShopifyAdminClient(
        shop_domain="demo.myshopify.com",
        client_id="client-id",
        client_secret="client-secret",
    )

    assert client._get_access_token() == "token-123"
    assert client._get_access_token() == "token-123"
    assert len(calls) == 1
    assert calls[0][0].endswith("/admin/oauth/access_token")
    assert calls[0][1]["data"]["grant_type"] == "client_credentials"


def test_create_demo_order_sends_real_sku(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/admin/oauth/access_token"):
            return FakeResponse({"access_token": "token-123", "expires_in": 86399})
        return FakeResponse({
            "data": {
                "orderCreate": {
                    "order": {"id": "gid://shopify/Order/123", "name": "#1001", "createdAt": "2026-08-24T14:00:00Z"},
                    "userErrors": [],
                }
            }
        })

    monkeypatch.setattr("app.shopify.httpx.post", fake_post)
    client = ShopifyAdminClient(
        shop_domain="demo.myshopify.com",
        client_id="client-id",
        client_secret="client-secret",
    )
    order = client.create_demo_order(sku="COSRX-SNL-100", unit_price=Decimal("24.90"))

    assert order["name"] == "#1001"
    graphql_call = calls[1][1]["json"]
    line = graphql_call["variables"]["order"]["lineItems"][0]
    assert line["sku"] == "COSRX-SNL-100"
    assert line["priceSet"]["shopMoney"]["amount"] == "24.90"
