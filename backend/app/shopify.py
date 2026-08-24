import base64
import hashlib
import hmac
import json
import os
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
        api_version: str | None = None,
    ) -> None:
        self.shop_domain = (shop_domain or os.getenv("SHOPIFY_SHOP_DOMAIN") or "").replace("https://", "").rstrip("/")
        self.access_token = access_token or os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.api_version = api_version or os.getenv("SHOPIFY_API_VERSION", "2026-07")

    @property
    def configured(self) -> bool:
        return bool(self.shop_domain and self.access_token)

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
        response = httpx.post(
            f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json",
            headers={"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"},
            json={"query": query, "variables": {"first": first}},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload["errors"]))

        orders = []
        for node in payload["data"]["orders"]["nodes"]:
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
