import os

from fastapi import FastAPI, Header, HTTPException

from .database import Database
from .models import EventResponse, MappingRequest, ShopifyOrder
from .service import ConnectorService

app = FastAPI(
    title="CommerceBridge Connector API",
    version="1.0.0",
    description="Reliable Shopify, marketplace and ERP order exchange demo.",
)
database = Database(os.getenv("COMMERCEBRIDGE_DB", "data/commercebridge.db"))
service = ConnectorService(database)


@app.get("/health")
def health():
    return {"status": "healthy", "connectors": ["shopify", "marketplace", "erp"]}


@app.post("/webhooks/shopify/orders", response_model=EventResponse)
def receive_shopify_order(
    order: ShopifyOrder,
    x_idempotency_key: str = Header(..., min_length=8),
):
    return service.process_shopify_order(order, x_idempotency_key)


@app.post("/mappings/{event_id}", response_model=EventResponse)
def create_mapping_and_retry(event_id: str, mapping: MappingRequest):
    database.upsert_mapping(mapping.external_sku, mapping.erp_sku, mapping.product_name)
    try:
        return service.retry(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Integration event not found") from error


@app.post("/events/{event_id}/retry", response_model=EventResponse)
def retry_event(event_id: str):
    try:
        return service.retry(event_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Integration event not found") from error


@app.get("/events")
def list_events():
    return [dict(row) for row in database.list_events()]
