import json
import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str = "commercebridge.db") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS product_mappings (
              external_sku TEXT PRIMARY KEY,
              erp_sku TEXT NOT NULL,
              product_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS integration_events (
              event_id TEXT PRIMARY KEY,
              idempotency_key TEXT UNIQUE NOT NULL,
              source TEXT NOT NULL,
              source_order_id TEXT NOT NULL,
              status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              payload TEXT NOT NULL,
              canonical_payload TEXT,
              error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.connection.executemany(
            "INSERT OR IGNORE INTO product_mappings VALUES (?, ?, ?)",
            [
                ("COSRX-SNL-100", "ERP-COS-0100", "COSRX Snail Essence 100ml"),
                ("BOJ-RLF-050", "ERP-BOJ-0050", "Beauty of Joseon Relief Sun 50ml"),
                ("SKIN1004-CEN-055", "ERP-SK1-0055", "Centella Ampoule 55ml"),
            ],
        )
        self.connection.commit()

    def mapping_for(self, external_sku: str):
        return self.connection.execute(
            "SELECT * FROM product_mappings WHERE external_sku = ?", (external_sku,)
        ).fetchone()

    def upsert_mapping(self, external_sku: str, erp_sku: str, product_name: str) -> None:
        self.connection.execute(
            """INSERT INTO product_mappings VALUES (?, ?, ?)
               ON CONFLICT(external_sku) DO UPDATE SET erp_sku=excluded.erp_sku,
               product_name=excluded.product_name""",
            (external_sku, erp_sku, product_name),
        )
        self.connection.commit()

    def event_by_key(self, key: str):
        return self.connection.execute(
            "SELECT * FROM integration_events WHERE idempotency_key = ?", (key,)
        ).fetchone()

    def event_by_id(self, event_id: str):
        return self.connection.execute(
            "SELECT * FROM integration_events WHERE event_id = ?", (event_id,)
        ).fetchone()

    def create_event(self, event_id: str, key: str, source_order_id: str, payload: dict) -> None:
        self.connection.execute(
            """INSERT INTO integration_events
               (event_id, idempotency_key, source, source_order_id, status, payload)
               VALUES (?, ?, 'shopify', ?, 'processing', ?)""",
            (event_id, key, source_order_id, json.dumps(payload, default=str)),
        )
        self.connection.commit()

    def update_event(self, event_id: str, *, status: str, attempts: int, error=None, canonical=None) -> None:
        self.connection.execute(
            """UPDATE integration_events SET status=?, attempts=?, error=?,
               canonical_payload=?, updated_at=CURRENT_TIMESTAMP WHERE event_id=?""",
            (status, attempts, error, json.dumps(canonical, default=str) if canonical else None, event_id),
        )
        self.connection.commit()

    def list_events(self):
        return self.connection.execute(
            "SELECT * FROM integration_events ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
