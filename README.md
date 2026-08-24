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

- **Real integration-ready:** Shopify webhook HMAC verification, official Shopify delivery ID deduplication, webhook payload normalization, automatic 24-hour Admin API token acquisition through client credentials, Shopify Admin GraphQL reconciliation, real test-order creation, persistent audit trail, missing-SKU recovery, retry/backoff, and configurable ERP HTTP delivery.
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
- `POST /shopify/setup/webhook` — registers the real `ORDERS_CREATE` callback against the configured public HTTPS URL.
- `POST /shopify/demo-order` — creates a real Shopify development-store order using GraphQL; the resulting signed webhook then comes back through the normal pipeline.
- `POST /reconcile/shopify` — queries recent Shopify orders through Admin GraphQL and queues orders missing from the local audit trail.
- `POST /mappings/{event_id}` — saves a missing SKU mapping and retries the same integration event.
- `POST /events/{event_id}/retry` — reprocesses a recoverable event.
- `GET /events` — operational audit trail.
- `GET /health` — shows whether Shopify Admin API and a real ERP are configured.

## Connect a Shopify development store

1. In Shopify Dev Dashboard, create a development store. Generated test data is optional.
2. Create a Dev Dashboard app, release a version with `read_orders,write_orders`, and install it on that dev store.
3. Copy the app **Client ID** and **Client secret** into `backend/.env` together with the store domain. CommerceBridge uses Shopify's client-credentials grant and refreshes the 24-hour Admin API token automatically.
4. Run FastAPI locally and expose port 8000 through any HTTPS tunnel. Put that HTTPS URL in `COMMERCEBRIDGE_PUBLIC_URL`.
5. Register the callback once:

```bash
curl -X POST http://localhost:8000/shopify/setup/webhook
```

   Or run `python scripts/register_shopify_webhook.py`.
6. In the live dashboard click **Create real Shopify order**. CommerceBridge calls Shopify GraphQL `orderCreate` using SKU `COSRX-SNL-100`; Shopify creates the order and independently sends the signed `ORDERS_CREATE` webhook back to CommerceBridge.
7. Use **Reconcile Shopify** to independently query recent orders and detect any order missing from the integration audit trail.

Only the Shopify account/store/app creation requires an interactive Shopify login. No long-lived Admin API token needs to be copied manually.

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
2. Click **Create real Shopify order** and show that the order is created in Shopify first, then arrives back through Shopify's signed webhook before appearing in CommerceBridge.
3. Replay a delivery ID in the demo scenario to show idempotency.
4. Send an unknown SKU; open **Recovery queue**, map it, and retry the same event.
5. Trigger the ERP outage scenario: three attempts are recorded before manual review.
6. Run **Reconcile Shopify** and explain why webhook-driven systems still need reconciliation.

## Tests

The backend suite currently has 11 passing tests covering successful delivery, duplicate webhooks, missing-SKU recovery, ERP retry history, raw-body HMAC verification, queued processing, the real webhook HTTP endpoint, client-credentials token caching, and real GraphQL demo-order payload construction.
