"""Register the ORDERS_CREATE webhook for a Shopify development store.

Required env vars:
  SHOPIFY_SHOP_DOMAIN
  SHOPIFY_ACCESS_TOKEN
  COMMERCEBRIDGE_PUBLIC_URL   e.g. https://api.example.com
Optional:
  SHOPIFY_API_VERSION         defaults to 2026-07
"""
import os
import sys

import httpx

shop = (os.getenv("SHOPIFY_SHOP_DOMAIN") or "").replace("https://", "").rstrip("/")
token = os.getenv("SHOPIFY_ACCESS_TOKEN")
public_url = (os.getenv("COMMERCEBRIDGE_PUBLIC_URL") or "").rstrip("/")
version = os.getenv("SHOPIFY_API_VERSION", "2026-07")

if not all([shop, token, public_url]):
    sys.exit("Set SHOPIFY_SHOP_DOMAIN, SHOPIFY_ACCESS_TOKEN and COMMERCEBRIDGE_PUBLIC_URL first.")

query = """
mutation RegisterOrdersCreate($topic: WebhookSubscriptionTopic!, $subscription: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $subscription) {
    webhookSubscription { id topic uri }
    userErrors { field message }
  }
}
"""
variables = {
    "topic": "ORDERS_CREATE",
    "subscription": {"uri": f"{public_url}/webhooks/shopify/orders/create"},
}
response = httpx.post(
    f"https://{shop}/admin/api/{version}/graphql.json",
    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
    json={"query": query, "variables": variables},
    timeout=10.0,
)
response.raise_for_status()
body = response.json()
print(body)
errors = (((body.get("data") or {}).get("webhookSubscriptionCreate") or {}).get("userErrors") or [])
if errors:
    sys.exit(1)
