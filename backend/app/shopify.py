import base64
import hashlib
import hmac
import json
import os
import time
from decimal import Decimal

import httpx

from .models import LineItem, ShopifyOrder


def verify_shopify_hmac(raw_body: bytes, received_hmac: str, secret: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    calculated = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(calculated, received_hmac)


def order_from_webhook(payload: dict, shop_domain: str | None = None) -> ShopifyOrder:
    customer = payload.get("customer") or {}
    customer_name = " ".join(filter(None, [customer.get("first_name"), customer.get("last_name")])).strip()
    if not customer_name:
        billing = payload.get("billing_address") or {}
        customer_name = billing.get("name") or payload.get("email") or "Shopify customer"

    line_items = []
    for item in payload.get("line_items") or []:
        sku = (item.get("sku") or "").strip()
        if not sku:
            sku = f"SHOPIFY-LINE-{item.get('id', 'UNKNOWN')}"
        line_items.append(
            LineItem(
                sku=sku,
                title=item.get("title") or item.get("name") or "Shopify item",
                quantity=int(item.get("quantity") or 0),
                unit_price=Decimal(str(item.get("price") or "0")),
            )
        )

    return ShopifyOrder(
        order_id=str(payload.get("id") or payload.get("order_number") or payload.get("name")),
        customer_name=customer_name,
        currency=str(payload.get("currency") or "EUR"),
        line_items=line_items,
        shop_domain=shop_domain,
    )


class ShopifyAdminClient:
    def __init__(
        self,
        shop_domain: str | None = None,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self.shop_domain = (shop_domain or os.getenv("SHOPIFY_SHOP_DOMAIN") or "").replace("https://", "").rstrip("/")
        self.access_token = access_token or os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.client_id = client_id or os.getenv("SHOPIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SHOPIFY_CLIENT_SECRET")
        self.api_version = api_version or os.getenv("SHOPIFY_API_VERSION", "2026-07")
        self._cached_token: str | None = None
        self._token_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.shop_domain and (self.access_token or (self.client_id and self.client_secret)))

    def _get_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        if not (self.shop_domain and self.client_id and self.client_secret):
            raise RuntimeError("Shopify Admin API is not configured")
        if self._cached_token and time.time() < self._token_expires_at - 60:
            return self._cached_token

        response = httpx.post(
            f"https://{self.shop_domain}/admin/oauth/access_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10.0,
        )
        if response.is_error:
            raise RuntimeError(
                f"Shopify token exchange failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"Shopify did not return an access token: {payload}")
        self._cached_token = token
        self._token_expires_at = time.time() + int(payload.get("expires_in") or 86399)
        return token

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        token = self._get_access_token()
        response = httpx.post(
            f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
            timeout=10.0,
        )
        if response.is_error:
            raise RuntimeError(
                f"Shopify GraphQL request failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload["errors"]))
        return payload.get("data") or {}

    def register_orders_create_webhook(self, callback_url: str) -> dict:
        query = """
        mutation RegisterOrdersCreate($topic: WebhookSubscriptionTopic!, $subscription: WebhookSubscriptionInput!) {
          webhookSubscriptionCreate(topic: $topic, webhookSubscription: $subscription) {
            webhookSubscription { id topic uri }
            userErrors { field message }
          }
        }
        """
        data = self._graphql(
            query,
            {
                "topic": "ORDERS_CREATE",
                "subscription": {"uri": callback_url},
            },
        )
        result = data.get("webhookSubscriptionCreate") or {}
        errors = result.get("userErrors") or []
        if errors:
            raise RuntimeError(json.dumps(errors))
        return result.get("webhookSubscription") or {}

    def create_demo_order(
        self,
        *,
        sku: str = "COSRX-SNL-100",
        title: str = "COSRX Snail Essence 100ml",
        quantity: int = 2,
        unit_price: Decimal = Decimal("24.90"),
        currency: str = "EUR",
    ) -> dict:
        query = """
        mutation CreateCommerceBridgeDemoOrder($order: OrderCreateOrderInput!) {
          orderCreate(order: $order) {
            order { id name createdAt }
            userErrors { field message }
          }
        }
        """
        variables = {
            "order": {
                "currency": currency,
                "email": "commercebridge-demo@example.com",
                "financialStatus": "PAID",
                "lineItems": [
                    {
                        "sku": sku,
                        "title": title,
                        "quantity": quantity,
                        "priceSet": {
                            "shopMoney": {
                                "amount": str(unit_price),
                                "currencyCode": currency,
                            }
                        },
                    }
                ],
                "note": "Created by CommerceBridge integration demo",
            }
        }
        data = self._graphql(query, variables)
        result = data.get("orderCreate") or {}
        errors = result.get("userErrors") or []
        if errors:
            raise RuntimeError(json.dumps(errors))
        return result.get("order") or {}

    def list_recent_orders(self, first: int = 25) -> list[ShopifyOrder]:
        if not self.configured:
            raise RuntimeError("Shopify Admin API is not configured")

        query = """
        query RecentOrders($first: Int!) {
          orders(first: $first, reverse: true, sortKey: CREATED_AT) {
            nodes {
              id
              name
              createdAt
              customer { firstName lastName }
              totalPriceSet { shopMoney { currencyCode } }
              lineItems(first: 50) {
                nodes {
                  sku
                  title
                  quantity
                  originalUnitPriceSet { shopMoney { amount } }
                }
              }
            }
          }
        }
        """
        payload = self._graphql(query, {"first": first})

        orders = []
        for node in (payload.get("orders") or {}).get("nodes") or []:
            customer = node.get("customer") or {}
            name = " ".join(filter(None, [customer.get("firstName"), customer.get("lastName")])).strip() or "Shopify customer"
            money = (node.get("totalPriceSet") or {}).get("shopMoney") or {}
            items = []
            for item in (node.get("lineItems") or {}).get("nodes") or []:
                price = ((item.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get("amount") or "0"
                sku = (item.get("sku") or "").strip() or f"SHOPIFY-LINE-{len(items)+1}"
                items.append(LineItem(sku=sku, title=item.get("title") or "Shopify item", quantity=item["quantity"], unit_price=Decimal(str(price))))
            orders.append(
                ShopifyOrder(
                    order_id=str(node["id"]),
                    customer_name=name,
                    currency=money.get("currencyCode") or "EUR",
                    line_items=items,
                    shop_domain=self.shop_domain,
                    created_at=node.get("createdAt"),
                )
            )
        return orders
