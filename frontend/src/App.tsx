"use client";

import { useMemo, useState } from "react";

type Status = "Completed" | "Needs review" | "Processing" | "Blocked duplicate";
type Order = { id: string; source: "Shopify" | "Marketplace" | "B2B EDI"; customer: string; amount: string; items: number; status: Status; time: string; };

const initialOrders: Order[] = [
  { id: "CB-1048", source: "Shopify", customer: "Müller Drogerie", amount: "€1,284.60", items: 18, status: "Completed", time: "10:42" },
  { id: "CB-1047", source: "B2B EDI", customer: "Beauty Plaza", amount: "€3,916.20", items: 42, status: "Completed", time: "10:31" },
  { id: "CB-1046", source: "Marketplace", customer: "Glow Market", amount: "€648.90", items: 9, status: "Needs review", time: "10:18" },
  { id: "CB-1045", source: "Shopify", customer: "Skin Studio Nord", amount: "€429.00", items: 6, status: "Processing", time: "10:14" },
  { id: "CB-1044", source: "Shopify", customer: "Seoul Select", amount: "€792.40", items: 12, status: "Completed", time: "09:58" },
];

const statusClass: Record<Status, string> = {
  Completed: "status status-success", "Needs review": "status status-review",
  Processing: "status status-processing", "Blocked duplicate": "status status-blocked",
};

export default function Home() {
  const [active, setActive] = useState("Overview");
  const [range, setRange] = useState("Today");
  const [orderRows, setOrderRows] = useState(initialOrders);
  const [dialog, setDialog] = useState<"sample" | "mapping" | "order" | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [mappingResolved, setMappingResolved] = useState(false);
  const [activities, setActivities] = useState([
    ["Invoice INV-8842 delivered", "ERP Gateway · 3 min ago", "success"],
    ["Order CB-1047 transformed", "B2B EDI · 11 min ago", "info"],
    ["SKU catalogue synced", "2,486 products · 28 min ago", "success"],
  ]);
  const reviewCount = orderRows.filter((order) => order.status === "Needs review").length;
  const filteredOrders = useMemo(() => active === "Exceptions" ? orderRows.filter((order) => order.status === "Needs review") : orderRows, [active, orderRows]);

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 3200);
  }

  function runScenario(kind: "valid" | "duplicate" | "timeout") {
    const id = kind === "duplicate" ? "CB-1048-DUP" : kind === "timeout" ? "CB-1050" : "CB-1049";
    const newOrder: Order = {
      id,
      source: kind === "timeout" ? "B2B EDI" : "Shopify",
      customer: kind === "timeout" ? "K-Beauty Partner" : "Han River Store",
      amount: kind === "timeout" ? "€2,118.40" : "€956.80",
      items: kind === "timeout" ? 26 : 14,
      status: kind === "duplicate" ? "Blocked duplicate" : kind === "timeout" ? "Needs review" : "Processing",
      time: "Now",
    };
    setOrderRows((current) => [newOrder, ...current.filter((order) => order.id !== id)]);
    setDialog(null);
    if (kind === "duplicate") {
      setActivities((current) => [["Duplicate webhook safely blocked", "Idempotency key shopify_1048 · now", "info"], ...current].slice(0, 4));
      notify("Duplicate detected — no second ERP order was created.");
      return;
    }
    if (kind === "timeout") {
      setActivities((current) => [["ERP delivery moved to retry queue", "Attempt 3/3 · now", "info"], ...current].slice(0, 4));
      notify("ERP timeout captured with full retry history.");
      return;
    }
    notify("Shopify webhook accepted and processing.");
    window.setTimeout(() => {
      setOrderRows((current) => current.map((order) => order.id === id ? { ...order, status: "Completed" } : order));
      setActivities((current) => [["Order CB-1049 delivered to ERP", "Shopify · just now", "success"], ...current].slice(0, 4));
      notify("CB-1049 validated, transformed and delivered in 1.6s.");
    }, 1200);
  }

  function resolveMapping() {
    setMappingResolved(true);
    setOrderRows((current) => current.map((order) => order.id === "CB-1046" ? { ...order, status: "Completed" } : order));
    setActivities((current) => [["SKU ANUA-HRT-250-P mapped", "ERP product ERP-AN-0250 · just now", "success"], ...current].slice(0, 4));
    setDialog(null);
    notify("Mapping saved — CB-1046 was reprocessed successfully.");
  }

  function openOrder(order: Order) {
    setSelectedOrder(order);
    setDialog("order");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-mark" aria-label="CommerceBridge home">
          <span className="brand-glyph">CB</span>
          <div><strong>CommerceBridge</strong><small>Integration control</small></div>
        </div>
        <nav className="nav-list">
          {["Overview", "Orders", "Exceptions", "Mappings"].map((item) => (
            <button key={item} className={active === item ? "nav-item active" : "nav-item"} onClick={() => setActive(item)}>
              <span className="nav-dot" />{item}{item === "Exceptions" && reviewCount > 0 && <b className="nav-count">{reviewCount}</b>}
            </button>
          ))}
        </nav>
        <div className="side-section">
          <span>Connections</span>
          <div className="connection"><i className="shopify">S</i><div>Shopify<small>Healthy</small></div><b /></div>
          <div className="connection"><i className="market">M</i><div>Marketplaces<small>Healthy</small></div><b /></div>
          <div className="connection"><i className="erp">E</i><div>ERP gateway<small>Healthy</small></div><b /></div>
        </div>
        <div className="sidebar-footer"><div className="avatar">MM</div><div><strong>Mazhar Munir</strong><small>Integration engineer</small></div></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">LIVE OPERATIONS</p><h1>{active}</h1></div>
          <div className="top-actions">
            <label className="range-select"><span className="sr-only">Reporting range</span><select value={range} onChange={(event) => setRange(event.target.value)}><option>Today</option><option>Last 7 days</option><option>Last 30 days</option></select></label>
            <button className="primary-button" onClick={() => setDialog("sample")}>Run sample order <span>→</span></button>
          </div>
        </header>
        <div className="notice-bar"><span className="live-pulse" /> All connectors operational<small>Last health check 24 seconds ago</small></div>

        <section className="metric-grid" aria-label="Integration metrics">
          <article className="metric-card featured"><div className="metric-label">ORDERS PROCESSED <span>↗ 12.4%</span></div><div className="metric-value">1,248</div><div className="mini-bars" aria-hidden="true">{[30,44,36,58,49,68,64,82,74,91,84,100].map((height, index) => <i key={index} style={{height: `${height}%`}} />)}</div></article>
          <article className="metric-card"><div className="metric-label">SUCCESS RATE <span>+0.8%</span></div><div className="metric-value">99.2<em>%</em></div><div className="metric-foot"><i className="good-dot" /> Above 98% target</div></article>
          <article className="metric-card"><div className="metric-label">AVG. PROCESSING</div><div className="metric-value">1.8<em>s</em></div><div className="metric-foot">P95 latency 3.2s</div></article>
          <article className="metric-card alert-card"><div className="metric-label">NEEDS ATTENTION</div><div className="metric-value">{reviewCount}</div><div className="metric-foot warn">{reviewCount ? "Review integration exceptions" : "Queue is clear"}</div></article>
        </section>

        <section className="content-grid">
          <article className="panel orders-panel">
            <div className="panel-heading"><div><p className="eyebrow">{active === "Mappings" ? "PRODUCT CATALOGUE" : "TRANSACTION STREAM"}</p><h2>{active === "Exceptions" ? "Exception queue" : active === "Mappings" ? "SKU mappings" : "Recent orders"}</h2></div><button className="text-button" onClick={() => setActive(active === "Orders" ? "Overview" : "Orders")}>{active === "Orders" ? "Back to overview" : "View all orders"} →</button></div>
            {active === "Mappings" ? (
              <div className="mapping-list">
                <div className="mapping-row mapping-head"><span>External SKU</span><span>ERP product</span><span>Source</span><span>State</span></div>
                {[
                  ["COSRX-SNL-100", "ERP-COS-0100", "Shopify"],
                  ["BOJ-RLF-050", "ERP-BOJ-0050", "Marketplace"],
                  ["ANUA-HRT-250-P", mappingResolved ? "ERP-AN-0250" : "Unmapped", "Marketplace"],
                  ["SKIN1004-CEN-055", "ERP-SK1-0055", "B2B EDI"],
                ].map((mapping) => <button className="mapping-row" key={mapping[0]} onClick={() => mapping[1] === "Unmapped" && setDialog("mapping")}><code>{mapping[0]}</code><code className={mapping[1] === "Unmapped" ? "unmapped" : ""}>{mapping[1]}</code><span>{mapping[2]}</span><b className={mapping[1] === "Unmapped" ? "status status-review" : "status status-success"}><i />{mapping[1] === "Unmapped" ? "Review" : "Active"}</b></button>)}
              </div>
            ) : <div className="order-table" role="table" aria-label="Recent integration orders">
              <div className="table-row table-head" role="row"><span>Order</span><span>Source</span><span>Customer</span><span>Amount</span><span>Status</span><span>Time</span></div>
              {filteredOrders.map((order) => (
                <button className="table-row data-row" role="row" key={order.id} onClick={() => openOrder(order)}>
                  <span className="order-id">{order.id}<small>{order.items} items</small></span>
                  <span><i className={`source-icon ${order.source.toLowerCase().replaceAll(" ", "-")}`}>{order.source.slice(0,1)}</i>{order.source}</span>
                  <span>{order.customer}</span><span className="amount">{order.amount}</span>
                  <span><b className={statusClass[order.status]}><i />{order.status}</b></span><span className="time">{order.time}</span>
                </button>
              ))}
            </div>}
          </article>

          <aside className="panel exception-panel">
            <div className="panel-heading compact"><div><p className="eyebrow">ACTION REQUIRED</p><h2>Exception queue</h2></div><span className="issue-count">{reviewCount} {reviewCount === 1 ? "issue" : "issues"}</span></div>
            {reviewCount > 0 ? <div className="exception-card">
              <div className="exception-top"><span className="exception-icon">!</span><div><strong>Unknown SKU mapping</strong><small>Order CB-1046 · Marketplace</small></div></div>
              <div className="code-block"><span>External SKU</span><code>ANUA-HRT-250-P</code></div>
              <p>No ERP product match was found. Map the product to continue processing.</p><button className="secondary-button" onClick={() => setDialog("mapping")}>Resolve mapping <span>→</span></button>
            </div> : <div className="empty-state"><span>✓</span><strong>Exception queue cleared</strong><small>All current orders have valid product mappings.</small></div>}
            <div className="activity"><p className="eyebrow">RECENT ACTIVITY</p><ul>
              {activities.map((item, index) => <li key={`${item[0]}-${index}`}><i className={item[2] === "success" ? "activity-success" : "activity-info"}>{item[2] === "success" ? "✓" : "↻"}</i><div><strong>{item[0]}</strong><small>{item[1]}</small></div></li>)}
            </ul></div>
          </aside>
        </section>
        <footer className="workspace-footer"><span>CommerceBridge demo environment</span><span>Python · FastAPI · REST · PostgreSQL · CI/CD</span></footer>
      </section>

      {toast && <div className="toast" role="status"><span>✓</span>{toast}</div>}

      {dialog && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setDialog(null)}>
        <section className="dialog" role="dialog" aria-modal="true" aria-label={dialog === "sample" ? "Run a sample order" : dialog === "mapping" ? "Resolve product mapping" : "Order details"}>
          <button className="dialog-close" aria-label="Close dialog" onClick={() => setDialog(null)}>×</button>

          {dialog === "sample" && <>
            <p className="eyebrow">INTEGRATION LAB</p><h2>Choose a reliability scenario</h2>
            <p className="dialog-intro">Each scenario sends a realistic commerce payload through validation, transformation and delivery.</p>
            <div className="scenario-list">
              <button onClick={() => runScenario("valid")}><i className="scenario-num">01</i><div><strong>Valid Shopify order</strong><small>Validate 14 items, map SKUs and deliver the canonical order to ERP.</small></div><span>Run →</span></button>
              <button onClick={() => runScenario("duplicate")}><i className="scenario-num">02</i><div><strong>Duplicate webhook</strong><small>Replay an existing idempotency key and safely block the second order.</small></div><span>Run →</span></button>
              <button onClick={() => runScenario("timeout")}><i className="scenario-num">03</i><div><strong>ERP timeout</strong><small>Simulate retries, capture the error and move the event to manual review.</small></div><span>Run →</span></button>
            </div>
          </>}

          {dialog === "mapping" && <>
            <p className="eyebrow">EXCEPTION CB-1046</p><h2>Map external product</h2>
            <p className="dialog-intro">Connect the marketplace SKU to a verified product in the ERP catalogue, then retry the order.</p>
            <div className="mapping-form">
              <label>External SKU<input value="ANUA-HRT-250-P" readOnly /></label>
              <label>ERP product<select defaultValue="ERP-AN-0250"><option value="ERP-AN-0250">ERP-AN-0250 · Anua Heartleaf Toner 250ml</option><option>ERP-AN-0150 · Anua Heartleaf Toner 150ml</option></select></label>
              <div className="validation-note"><span>✓</span><div><strong>Product data validated</strong><small>EAN, unit size and VAT category match.</small></div></div>
              <button className="primary-button full-button" onClick={resolveMapping}>Save mapping & retry order <span>→</span></button>
            </div>
          </>}

          {dialog === "order" && selectedOrder && <>
            <p className="eyebrow">ORDER TRACE</p><div className="order-dialog-title"><h2>{selectedOrder.id}</h2><b className={statusClass[selectedOrder.status]}><i />{selectedOrder.status}</b></div>
            <p className="dialog-intro">{selectedOrder.source} → Canonical commerce model → ERP Gateway</p>
            <div className="trace-grid">
              <div><span>Customer</span><strong>{selectedOrder.customer}</strong></div><div><span>Order value</span><strong>{selectedOrder.amount}</strong></div><div><span>Line items</span><strong>{selectedOrder.items}</strong></div><div><span>Idempotency</span><strong>Verified</strong></div>
            </div>
            <div className="timeline">
              <div className="done"><i>✓</i><div><strong>Webhook authenticated</strong><small>HMAC signature and idempotency key verified</small></div><time>0.1s</time></div>
              <div className="done"><i>✓</i><div><strong>Payload validated</strong><small>Customer, VAT, quantities and prices accepted</small></div><time>0.4s</time></div>
              <div className={selectedOrder.status === "Needs review" ? "waiting" : "done"}><i>{selectedOrder.status === "Needs review" ? "!" : "✓"}</i><div><strong>SKU mapping</strong><small>{selectedOrder.status === "Needs review" ? "Manual review required" : `${selectedOrder.items} line items mapped`}</small></div><time>0.8s</time></div>
              <div className={selectedOrder.status === "Completed" ? "done" : "waiting"}><i>{selectedOrder.status === "Completed" ? "✓" : "·"}</i><div><strong>ERP delivery</strong><small>{selectedOrder.status === "Completed" ? "Order confirmation received" : "Waiting for prerequisites"}</small></div><time>{selectedOrder.status === "Completed" ? "1.6s" : "—"}</time></div>
            </div>
            <details className="payload"><summary>View canonical payload</summary><pre>{JSON.stringify({ order_id: selectedOrder.id, source: selectedOrder.source.toLowerCase().replace(" ", "_"), customer: selectedOrder.customer, line_items: selectedOrder.items, currency: "EUR", idempotency_key: `commerce_${selectedOrder.id.toLowerCase()}` }, null, 2)}</pre></details>
          </>}
        </section>
      </div>}
    </main>
  );
}
