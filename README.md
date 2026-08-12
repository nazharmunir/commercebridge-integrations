# CommerceBridge

CommerceBridge is a commerce-to-ERP integration control center built as a targeted portfolio project for Kencana. It demonstrates webhook validation, canonical order transformation, idempotency, SKU mapping recovery, retry handling, and an operational audit trail.

## Frontend

The interactive dashboard is a Vite + React + TypeScript application.

```bash
cd frontend
npm install
npm run dev
```

Production build:

```bash
npm run build
```

## Backend reference implementation

The backend contains a FastAPI, Pydantic, and SQLite implementation of the connector workflow.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload
```

## Portfolio demo scenarios

- Valid Shopify webhook: validates, transforms, and delivers an order.
- Duplicate webhook: blocks a second ERP order through idempotency.
- ERP timeout: captures retry history and moves the order to review.
- Missing SKU mapping: resolves the mapping and reprocesses the order.
