import json
import os
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .database import Database
from .models import EventResponse, MappingRequest, ReconciliationResult, ShopifyOrder, WebhookAck
from .service import ConnectorService
from .shopify import ShopifyAdminClient, order_from_webhook, verify_shopify_hmac

app = FastAPI(
    title="CommerceBridge Connector API",
    version="2.0.0",
    description="Shopify-to-ERP integration demo with verified webhooks, idempotency, retries and reconciliation.",
)

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

database = Database(os.getenv("COMMERCEBRIDGE_DB", "data/commercebridge.db"))
service = ConnectorService(database)
shopify = ShopifyAdminClient()


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "connectors": {
            "shopify_webhook": "configured" if (os.getenv("SHOPIFY_WEBHOOK_SECRET") or os.getenv("SHOPIFY_CLIENT_SECRET")) else "demo_mode",
            "shopify_admin_api": "configured" if shopify.configured else "not_configured",
            "erp": "configured" if os.getenv("ERP_BASE_URL") else "simulator",
        },
    }


@app.post("/webhooks/shopify/orders/create", response_model=WebhookAck, status_code=202)
async def receive_real_shopify_order(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_webhook_id: str = Header(...),
    x_shopify_shop_domain: str = Header(...),
    x_shopify_topic: str = Header(default="orders/create"),
):
    raw_body = await request.body()
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET") or os.getenv("SHOPIFY_CLIENT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="SHOPIFY_WEBHOOK_SECRET is not configured")
    if not verify_shopify_hmac(raw_body, x_shopify_hmac_sha256, secret):
        raise HTTPException(status_code=401, detail="Invalid Shopify HMAC signature")

    try:
        payload = json.loads(raw_body)
        order = order_from_webhook(payload, x_shopify_shop_domain)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Shopify order payload: {exc}") from exc

    queued = service.enqueue_shopify_order(order, x_shopify_webhook_id, topic=x_shopify_topic)
    if queued.status != "duplicate":
        background_tasks.add_task(service.process_event, queued.event_id)

    return WebhookAck(
        accepted=True,
        duplicate=queued.status == "duplicate",
        event_id=queued.event_id,
        webhook_id=x_shopify_webhook_id,
        status=queued.status,
    )


@app.post("/demo/shopify/orders", response_model=EventResponse)
def receive_demo_shopify_order(
    order: ShopifyOrder,
    background_tasks: BackgroundTasks,
    x_idempotency_key: str | None = Header(default=None),
):
    key = x_idempotency_key or f"demo_{uuid4().hex}"
    queued = service.enqueue_shopify_order(order, key)
    if queued.status != "duplicate":
        background_tasks.add_task(service.process_event, queued.event_id)
    return queued


@app.post("/shopify/setup/webhook")
def setup_shopify_webhook():
    if not shopify.configured:
        raise HTTPException(status_code=503, detail="Set SHOPIFY_SHOP_DOMAIN and Shopify app credentials first")
    public_url = (os.getenv("COMMERCEBRIDGE_PUBLIC_URL") or "").rstrip("/")
    if not public_url.startswith("https://"):
        raise HTTPException(status_code=503, detail="COMMERCEBRIDGE_PUBLIC_URL must be a public HTTPS URL")
    try:
        subscription = shopify.register_orders_create_webhook(
            f"{public_url}/webhooks/shopify/orders/create"
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Shopify webhook registration failed: {exc}") from exc
    return {"registered": True, "subscription": subscription}


@app.post("/shopify/demo-order")
def create_real_shopify_demo_order():
    if not shopify.configured:
        raise HTTPException(status_code=503, detail="Shopify Admin API is not configured")
    try:
        order = shopify.create_demo_order()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Shopify order creation failed: {exc}") from exc
    return {"created": True, "order": order, "message": "Shopify created the order; wait for the signed ORDERS_CREATE webhook."}


@app.post("/reconcile/shopify", response_model=ReconciliationResult)
def reconcile_shopify(background_tasks: BackgroundTasks, limit: int = 25):
    if not shopify.configured:
        raise HTTPException(status_code=503, detail="SHOPIFY_SHOP_DOMAIN / SHOPIFY_ACCESS_TOKEN are not configured")
    try:
        orders = shopify.list_recent_orders(first=min(max(limit, 1), 100))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Shopify reconciliation failed: {exc}") from exc

    queued = 0
    duplicates = 0
    event_ids = []
    for order in orders:
        if database.event_by_order_id(order.order_id):
            duplicates += 1
            continue
        key = f"reconcile:{order.shop_domain}:{order.order_id}"
        event = service.enqueue_shopify_order(order, key, topic="reconciliation")
        event_ids.append(event.event_id)
        if event.status == "duplicate":
            duplicates += 1
        else:
            queued += 1
            background_tasks.add_task(service.process_event, event.event_id)

    return ReconciliationResult(
        checked=len(orders),
        missing=queued,
        queued=queued,
        duplicates=duplicates,
        event_ids=event_ids,
    )


@app.post("/mappings/{event_id}", response_model=EventResponse)
def create_mapping_and_retry(event_id: str, mapping: MappingRequest):
    database.upsert_mapping(mapping.external_sku, mapping.erp_sku, mapping.product_name)
    try:
        return service.retry(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Integration event not found") from error


@app.get("/mappings")
def list_mappings():
    return [dict(row) for row in database.list_mappings()]


@app.post("/events/{event_id}/retry", response_model=EventResponse)
def retry_event(event_id: str):
    try:
        return service.retry(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Integration event not found") from error


@app.get("/events")
def list_events(limit: int = 100):
    return [dict(row) for row in database.list_events(min(max(limit, 1), 500))]
