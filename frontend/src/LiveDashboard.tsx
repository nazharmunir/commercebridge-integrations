import { useEffect, useMemo, useState } from "react";

type ApiEvent = {
  event_id: string; idempotency_key: string; source_order_id: string; status: string;
  attempts: number; payload: string; canonical_payload?: string | null; error?: string | null;
  erp_reference?: string | null; processing_ms?: number | null; updated_at?: string;
};
type Mapping = { external_sku: string; erp_sku: string; product_name: string };
type Health = { connectors?: Record<string, string> };
type Row = { id: string; customer: string; items: number; amount: string; status: string; time: string; event: ApiEvent };

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const demoRows = [
  { id: "CB-1048", customer: "Müller Drogerie", items: 18, amount: "€1,284.60", status: "completed", time: "10:42" },
  { id: "CB-1046", customer: "Glow Market", items: 9, amount: "€648.90", status: "needs_review", time: "10:18" },
];

function parse(value?: string | null) { try { return value ? JSON.parse(value) : null; } catch { return null; } }
function badge(status: string) {
  if (status === "completed") return "status status-success";
  if (status === "needs_review") return "status status-review";
  if (status === "duplicate") return "status status-blocked";
  return "status status-processing";
}
function label(status: string) {
  return ({ completed: "Completed", needs_review: "Needs review", duplicate: "Blocked duplicate", queued: "Queued", processing: "Processing" } as Record<string,string>)[status] || status;
}
function toRow(event: ApiEvent): Row {
  const payload = parse(event.payload) || {};
  const canonical = parse(event.canonical_payload) || {};
  const items = payload.line_items || [];
  const total = items.reduce((sum: number, item: any) => sum + Number(item.quantity || 0) * Number(item.unit_price || 0), 0);
  const source = String(event.source_order_id).startsWith("gid://") ? String(event.source_order_id).split("/").pop() : event.source_order_id;
  return {
    id: canonical.commerce_order_id || `CB-${source}`,
    customer: payload.customer_name || "Shopify customer",
    items: items.length,
    amount: new Intl.NumberFormat("de-DE", { style: "currency", currency: payload.currency || "EUR" }).format(total),
    status: event.status,
    time: event.updated_at ? new Date(`${event.updated_at}Z`).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Now",
    event,
  };
}

export default function LiveDashboard() {
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [health, setHealth] = useState<Health>({});
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"scenarios" | "trace" | "mapping" | null>(null);
  const [selected, setSelected] = useState<Row | null>(null);
  const [erpSku, setErpSku] = useState("ERP-AN-0250");

  const rows = useMemo(() => events.map(toRow), [events]);
  const visibleRows: any[] = rows.length ? rows : demoRows;
  const review = rows.find((row) => row.status === "needs_review");
  const success = rows.length ? Math.round(rows.filter(r => r.status === "completed").length / rows.length * 1000) / 10 : 99.2;

  function notify(text: string) { setToast(text); window.setTimeout(() => setToast(null), 3200); }

  async function refresh(silent = true) {
    try {
      const [ev, map, hp] = await Promise.all([fetch(`${API_URL}/events?limit=50`), fetch(`${API_URL}/mappings`), fetch(`${API_URL}/health`)]);
      if (!ev.ok || !map.ok || !hp.ok) throw new Error("Backend unavailable");
      setEvents(await ev.json()); setMappings(await map.json()); setHealth(await hp.json()); setOnline(true);
    } catch (error) { setOnline(false); if (!silent) notify(error instanceof Error ? error.message : "Backend unavailable"); }
  }

  useEffect(() => { refresh(); const timer = window.setInterval(() => refresh(), 5000); return () => clearInterval(timer); }, []);

  async function demo(kind: "valid" | "duplicate" | "missing" | "timeout") {
    setBusy(true);
    try {
      const suffix = Date.now();
      const payload = {
        order_id: String(suffix), customer_name: "Han River Store", currency: "EUR",
        line_items: [{ sku: kind === "missing" ? "ANUA-HRT-250-P" : "COSRX-SNL-100", title: "K-Beauty Product", quantity: 2, unit_price: "24.90", vat_rate: "0.19" }],
        simulate_erp_timeout: kind === "timeout",
      };
      const key = `demo-${kind}-${suffix}`;
      const send = () => fetch(`${API_URL}/demo/shopify/orders`, { method: "POST", headers: { "Content-Type": "application/json", "X-Idempotency-Key": key }, body: JSON.stringify(payload) });
      const first = await send(); if (!first.ok) throw new Error((await first.json()).detail || "Demo failed");
      if (kind === "duplicate") { const second = await send(); if (!second.ok) throw new Error("Duplicate replay failed"); }
      notify(kind === "duplicate" ? "Same Shopify delivery ID replayed — duplicate blocked." : kind === "missing" ? "Unknown SKU routed to recovery queue." : kind === "timeout" ? "ERP outage recorded after three attempts." : "Order acknowledged, queued and delivered to ERP.");
      setDialog(null); setTimeout(() => refresh(), 400); setTimeout(() => refresh(), 1200);
    } catch (error) { notify(error instanceof Error ? error.message : "Scenario failed"); }
    finally { setBusy(false); }
  }

  async function reconcile() {
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/reconcile/shopify?limit=25`, { method: "POST" });
      const body = await response.json(); if (!response.ok) throw new Error(body.detail || "Reconciliation failed");
      notify(`Checked ${body.checked} Shopify orders; ${body.missing} missing order(s) queued.`); setTimeout(() => refresh(), 500);
    } catch (error) { notify(error instanceof Error ? error.message : "Reconciliation failed"); }
    finally { setBusy(false); }
  }

  function openTrace(row: any) { if (!row.event) return; setSelected(row); setDialog("trace"); }
  function openMapping() {
    if (!review) return notify("Run the unknown-SKU scenario first.");
    setSelected(review); const sku = review.event.error?.replace("Unknown SKU mapping: ", "").split(",")[0] || "ANUA-HRT-250-P";
    setErpSku(sku === "ANUA-HRT-250-P" ? "ERP-AN-0250" : `ERP-${sku.replace(/[^A-Z0-9]/gi, "-").toUpperCase()}`); setDialog("mapping");
  }
  async function saveMapping() {
    if (!selected?.event) return;
    const sku = selected.event.error?.replace("Unknown SKU mapping: ", "").split(",")[0]; if (!sku) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/mappings/${selected.event.event_id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ external_sku: sku, erp_sku: erpSku, product_name: `Mapped product ${sku}` }) });
      const body = await response.json(); if (!response.ok) throw new Error(body.detail || "Mapping failed");
      notify(`Mapping saved; same event retried to ${body.status}.`); setDialog(null); await refresh(false);
    } catch (error) { notify(error instanceof Error ? error.message : "Mapping failed"); }
    finally { setBusy(false); }
  }

  const shopifyApi = health.connectors?.shopify_admin_api || "not_configured";
  const erp = health.connectors?.erp || "simulator";

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand-mark"><span className="brand-glyph">CB</span><div><strong>CommerceBridge</strong><small>Integration control</small></div></div>
      <nav className="nav-list"><button className="nav-item active"><span className="nav-dot" />Live operations</button><button className="nav-item" onClick={() => setDialog("scenarios")}><span className="nav-dot" />Integration lab</button></nav>
      <div className="side-section"><span>Connections</span>
        <div className="connection"><i className="shopify">S</i><div>Shopify webhook<small>{online ? "Listening" : "Presentation fallback"}</small></div><b /></div>
        <div className="connection"><i className="market">G</i><div>Admin GraphQL<small>{shopifyApi}</small></div><b /></div>
        <div className="connection"><i className="erp">E</i><div>ERP gateway<small>{erp}</small></div><b /></div>
      </div>
      <div className="sidebar-footer"><div className="avatar">MM</div><div><strong>Mazhar Munir</strong><small>Integration engineer</small></div></div>
    </aside>

    <section className="workspace">
      <header className="topbar"><div><p className="eyebrow">SHOPIFY → ERP</p><h1>Live operations</h1></div><div className="top-actions"><button className="secondary-button" disabled={busy} onClick={reconcile}>Reconcile Shopify</button><button className="primary-button" disabled={busy} onClick={() => setDialog("scenarios")}>Run scenario <span>→</span></button></div></header>
      <div className="notice-bar"><span className="live-pulse" />{online ? "Backend live · verified webhook pipeline ready" : "Presentation fallback · point VITE_API_URL at FastAPI for live events"}<small>{online ? API_URL : "Static rows shown safely"}</small></div>

      <section className="metric-grid">
        <article className="metric-card featured"><div className="metric-label">EVENTS IN VIEW</div><div className="metric-value">{visibleRows.length}</div><div className="metric-foot">Persistent integration audit trail</div></article>
        <article className="metric-card"><div className="metric-label">SUCCESS RATE</div><div className="metric-value">{success}<em>%</em></div><div className="metric-foot">ERP delivery outcome</div></article>
        <article className="metric-card"><div className="metric-label">SHOPIFY ADMIN API</div><div className="metric-value" style={{fontSize:24}}>{shopifyApi === "configured" ? "LIVE" : "READY"}</div><div className="metric-foot">2026-07 GraphQL reconciliation</div></article>
        <article className="metric-card alert-card"><div className="metric-label">NEEDS ATTENTION</div><div className="metric-value">{rows.filter(r => r.status === "needs_review").length}</div><div className="metric-foot warn">Recoverable exceptions</div></article>
      </section>

      <section className="content-grid">
        <article className="panel orders-panel">
          <div className="panel-heading"><div><p className="eyebrow">TRANSACTION STREAM</p><h2>Recent integration events</h2></div><button className="text-button" onClick={() => refresh(false)}>Refresh →</button></div>
          <div className="order-table"><div className="table-row table-head"><span>Order</span><span>Source</span><span>Customer</span><span>Amount</span><span>Status</span><span>Time</span></div>
            {visibleRows.map((row: any) => <button className="table-row data-row" key={`${row.id}-${row.event?.event_id || row.time}`} onClick={() => openTrace(row)}>
              <span className="order-id">{row.id}<small>{row.items} items</small></span><span><i className="source-icon shopify">S</i>Shopify</span><span>{row.customer}</span><span className="amount">{row.amount}</span><span><b className={badge(row.status)}><i />{label(row.status)}</b></span><span className="time">{row.time}</span>
            </button>)}
          </div>
        </article>

        <aside className="panel exception-panel"><div className="panel-heading compact"><div><p className="eyebrow">ACTION REQUIRED</p><h2>Recovery queue</h2></div></div>
          {review ? <div className="exception-card"><div className="exception-top"><span className="exception-icon">!</span><div><strong>{review.event.error?.startsWith("Unknown SKU") ? "Unknown SKU mapping" : "ERP delivery failure"}</strong><small>{review.id} · {review.event.event_id}</small></div></div><div className="code-block"><span>Error</span><code>{review.event.error || "needs_review"}</code></div><p>Fix the root cause and retry the same persisted event instead of recreating the order.</p>{review.event.error?.startsWith("Unknown SKU") && <button className="secondary-button" onClick={openMapping}>Map SKU & retry <span>→</span></button>}</div> : <div className="empty-state"><span>✓</span><strong>Recovery queue cleared</strong><small>No current event requires manual intervention.</small></div>}
          <div className="activity"><p className="eyebrow">PRODUCTION TOUCHES</p><ul><li><i className="activity-success">✓</i><div><strong>HMAC before parsing</strong><small>Raw Shopify request body</small></div></li><li><i className="activity-success">✓</i><div><strong>Delivery ID deduplication</strong><small>X-Shopify-Webhook-Id is unique</small></div></li><li><i className="activity-info">↻</i><div><strong>Independent reconciliation</strong><small>Admin GraphQL catches missed orders</small></div></li></ul></div>
        </aside>
      </section>
      <footer className="workspace-footer"><span>CommerceBridge reliability demo</span><span>React · FastAPI · Shopify Webhooks · GraphQL · ERP Gateway</span></footer>
    </section>

    {toast && <div className="toast" role="status"><span>✓</span>{toast}</div>}
    {dialog && <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setDialog(null)}><section className="dialog"><button className="dialog-close" onClick={() => setDialog(null)}>×</button>
      {dialog === "scenarios" && <><p className="eyebrow">INTEGRATION LAB</p><h2>Run a backend scenario</h2><p className="dialog-intro">Each button persists a real FastAPI integration event.</p><div className="scenario-list"><button onClick={() => demo("valid")}><i className="scenario-num">01</i><div><strong>Valid Shopify order</strong><small>Queue, map, transform and ERP-confirm.</small></div><span>Run →</span></button><button onClick={() => demo("duplicate")}><i className="scenario-num">02</i><div><strong>Duplicate delivery</strong><small>Replay the same Shopify delivery ID.</small></div><span>Run →</span></button><button onClick={() => demo("missing")}><i className="scenario-num">03</i><div><strong>Unknown Shopify SKU</strong><small>Route to review, map and retry.</small></div><span>Run →</span></button><button onClick={() => demo("timeout")}><i className="scenario-num">04</i><div><strong>ERP outage</strong><small>Three attempts with exponential backoff.</small></div><span>Run →</span></button></div></>}
      {dialog === "mapping" && selected && <><p className="eyebrow">RECOVERY ACTION</p><h2>Map external SKU & retry</h2><div className="mapping-form"><label>Event<input value={selected.event.event_id} readOnly /></label><label>Missing SKU<input value={selected.event.error?.replace("Unknown SKU mapping: ", "").split(",")[0] || ""} readOnly /></label><label>ERP product<input value={erpSku} onChange={e => setErpSku(e.target.value)} /></label><button className="primary-button full-button" disabled={busy} onClick={saveMapping}>Save mapping & retry same event <span>→</span></button></div></>}
      {dialog === "trace" && selected && <><p className="eyebrow">END-TO-END TRACE</p><div className="order-dialog-title"><h2>{selected.id}</h2><b className={badge(selected.status)}><i />{label(selected.status)}</b></div><p className="dialog-intro">Shopify → verified webhook → canonical model → ERP gateway</p><div className="trace-grid"><div><span>Event ID</span><strong>{selected.event.event_id}</strong></div><div><span>Webhook ID</span><strong>{selected.event.idempotency_key}</strong></div><div><span>Attempts</span><strong>{selected.event.attempts}</strong></div><div><span>ERP reference</span><strong>{selected.event.erp_reference || "—"}</strong></div></div><div className="timeline"><div className="done"><i>✓</i><div><strong>Webhook authenticated</strong><small>HMAC SHA-256 on raw body</small></div><time>HTTP</time></div><div className="done"><i>✓</i><div><strong>Delivery deduplicated</strong><small>Unique Shopify delivery ID</small></div><time>ACK</time></div><div className={selected.status === "needs_review" ? "waiting" : "done"}><i>{selected.status === "needs_review" ? "!" : "✓"}</i><div><strong>Mapping & transformation</strong><small>{selected.event.error || `${selected.items} items normalized`}</small></div><time>MAP</time></div><div className={selected.status === "completed" ? "done" : "waiting"}><i>{selected.status === "completed" ? "✓" : "·"}</i><div><strong>ERP delivery</strong><small>{selected.event.erp_reference || "Waiting / manual review"}</small></div><time>{selected.event.processing_ms ? `${selected.event.processing_ms}ms` : "—"}</time></div></div><details className="payload"><summary>View persisted Shopify payload</summary><pre>{JSON.stringify(parse(selected.event.payload), null, 2)}</pre></details></>}
    </section></div>}
  </main>;
}
