"""Register Shopify ORDERS_CREATE against the public CommerceBridge backend.

Required env vars:
  SHOPIFY_SHOP_DOMAIN
  SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET
    OR SHOPIFY_ACCESS_TOKEN
  COMMERCEBRIDGE_PUBLIC_URL
"""
import os
import sys

from app.shopify import ShopifyAdminClient

public_url = (os.getenv("COMMERCEBRIDGE_PUBLIC_URL") or "").rstrip("/")
if not public_url.startswith("https://"):
    sys.exit("Set COMMERCEBRIDGE_PUBLIC_URL to the HTTPS tunnel/backend URL first.")

client = ShopifyAdminClient()
if not client.configured:
    sys.exit("Set SHOPIFY_SHOP_DOMAIN plus client credentials (or SHOPIFY_ACCESS_TOKEN).")

subscription = client.register_orders_create_webhook(
    f"{public_url}/webhooks/shopify/orders/create"
)
print(subscription)
