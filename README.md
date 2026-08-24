# CommerceBridge

CommerceBridge is a Shopify-to-ERP integration control center built as a targeted portfolio project for Kencana. The v2 flow moves the demo from browser-only simulation to a backend-driven integration lifecycle: verified Shopify webhooks, fast acknowledgement, persistent idempotency, canonical order mapping, ERP retry/recovery, and GraphQL reconciliation for missed orders.

## Architecture

```text
Shopify ORDERS_CREATE webhook
        |
        | HMAC SHA-256 + X-Shopify-Webhook-Id
        v
FastAPI webhook endpoint -----> 202 acknowledgement
        |
        v
Persistent integration event (queued)
        |
        v
ConnectorService -> SKU mapping -> canonical order -> ERP gateway
        |                                      |
        | missing mapping / repeated failure   | confirmation
        v                                      v
needs_review -----------------------------> completed
        |
        +--> map SKU + retry same event

Shopify Admin GraphQL API ---> reconciliation ---> enqueue orders missing from audit trail
```

## What is real vs simulated

- **Real integration-ready:** Shopify webhook HMAC verification, official Shopify delivery ID deduplication, webhook payload normalization, Shopify Admin GraphQL reconciliation, persistent audit trail, missing-SKU recovery, retry/backoff, and configurable ERP HTTP delivery.
- **Demo fallback:** when `ERP_BASE_URL` is not configured, the ERP gateway returns a generated confirmation reference so the project remains runnable without access to a proprietary ERP.
- The React dashboard has a presentation fallback if the backend is offline, but switches to persisted FastAPI events when `VITE_API_URL` is reachable.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # export values using your preferred env loader
pytest -q
uvicorn app.main:app --reload
```

Important endpoints:

- `POST /webhooks/shopify/orders/create` — verified real Shopify webhook; uses `X-Shopify-Webhook-Id` as the unique delivery key.
- `POST /demo/shopify/orders` — interview/demo scenario endpoint without Shopify credentials.
- `POST /reconcile/shopify` — queries recent Shopify orders through Admin GraphQL and queues orders missing from the local audit trail.
- `POST /mappings/{event_id}` — saves a missing SKU mapping and retries the same integration event.
- `POST /events/{event_id}/retry` — reprocesses a recoverable event.
- `GET /events` — operational audit trail.
- `GET /health` — shows whether Shopify Admin API and a real ERP are configured.

## Connect a Shopify development store

1. Create/install a Shopify app on a development store with order read access.
2. Configure the variables in `backend/.env.example`. `SHOPIFY_WEBHOOK_SECRET` is the app client secret used to verify raw webhook deliveries.
3. Deploy the backend to an HTTPS URL.
4. Register the `ORDERS_CREATE` subscription:

```bash
cd backend
python scripts/register_shopify_webhook.py
```

5. Create an order in the development store. Shopify will push it to `/webhooks/shopify/orders/create`; CommerceBridge acknowledges it, persists the delivery ID, and processes it after the HTTP response.
6. Use **Reconcile Shopify** in the dashboard to independently query recent orders and detect an order that is missing from the integration audit trail.

## Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Set `VITE_API_URL` to the deployed FastAPI backend for the live demo.

## Interview demo sequence

1. Show `/health`: Shopify webhook + Admin API + ERP gateway states are visible.
2. Create an actual order in the Shopify development store and watch it appear in CommerceBridge.
3. Replay a delivery ID in the demo scenario to show idempotency.
4. Send an unknown SKU; open **Recovery queue**, map it, and retry the same event.
5. Trigger the ERP outage scenario: three attempts are recorded before manual review.
6. Run **Reconcile Shopify** and explain why webhook-driven systems still need reconciliation.

## Tests

The backend tests cover successful delivery, duplicate webhooks, missing-SKU recovery, ERP retry history, raw-body HMAC verification, Shopify webhook normalization, queued processing, and the real webhook HTTP endpoint.
