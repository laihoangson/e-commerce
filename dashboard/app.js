// RetailLens dashboard - two tabs (Real Olist / Live synthetic), hybrid fetch.
//
// All computed endpoints go through the FastAPI layer with a ?source= filter.
// The map uses Leaflet proportional-symbol markers at Brazilian state centroids
// (lighter and clearer than dense choropleth polygons for this data).

const API = () => CONFIG.API_BASE.replace(/\/+$/, "");
const fmtBRL = (n) => "R$" + Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const fmtNum = (n) => Number(n).toLocaleString("pt-BR");

async function apiGet(path) {
  const res = await fetch(API() + path);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}
function showError(elId, msg) {
  const el = document.getElementById(elId);
  if (el) el.innerHTML = `<div class="error">${msg}<br/>Render free tier may sleep; first load can take ~30-50s. Reload shortly.</div>`;
}

// Approximate centroids of Brazilian states for the proportional-symbol map.
const STATE_CENTROIDS = {
  AC: [-9.0, -70.5], AL: [-9.6, -36.7], AP: [1.4, -51.8], AM: [-4.1, -63.0],
  BA: [-12.5, -41.7], CE: [-5.2, -39.6], DF: [-15.8, -47.9], ES: [-19.6, -40.3],
  GO: [-15.9, -49.6], MA: [-5.0, -45.3], MT: [-12.6, -55.4], MS: [-20.5, -54.6],
  MG: [-18.5, -44.5], PA: [-4.0, -52.5], PB: [-7.1, -36.8], PR: [-24.5, -51.5],
  PE: [-8.4, -37.9], PI: [-7.7, -42.7], RJ: [-22.2, -42.7], RN: [-5.8, -36.5],
  RS: [-30.0, -53.5], RO: [-10.9, -62.8], RR: [2.1, -61.4], SC: [-27.2, -50.5],
  SP: [-22.2, -48.7], SE: [-10.6, -37.4], TO: [-10.2, -48.3],
};

const maps = {};

function renderMap(containerId, legendId, rows) {
  if (typeof L === "undefined") {
    document.getElementById(containerId).innerHTML =
      '<div class="error">Map library not loaded.</div>';
    return;
  }
  if (maps[containerId]) { maps[containerId].remove(); }
  const map = L.map(containerId, { attributionControl: false, zoomControl: true })
    .setView([-14.5, -52], 4);
  maps[containerId] = map;
  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    { maxZoom: 8, minZoom: 3 }
  ).addTo(map);

  const maxRev = Math.max(...rows.map((r) => Number(r.revenue)), 1);
  rows.forEach((r) => {
    const c = STATE_CENTROIDS[r.state];
    if (!c) return;
    const frac = Number(r.revenue) / maxRev;
    const radius = 6 + Math.sqrt(frac) * 34;
    L.circleMarker(c, {
      radius,
      fillColor: "#e8a33d",
      fillOpacity: 0.35 + frac * 0.45,
      color: "#e8a33d",
      weight: 1,
    })
      .bindPopup(
        `<b>${r.state}</b><br/>${fmtBRL(r.revenue)}<br/>${fmtNum(r.orders)} orders`
      )
      .addTo(map);
  });

  document.getElementById(legendId).innerHTML =
    '<span><span class="legend-swatch" style="background:#e8a33d"></span>Circle size &amp; opacity scale with revenue</span>';

  // Leaflet needs a size recalculation when its container becomes visible.
  setTimeout(() => map.invalidateSize(), 200);
}

async function loadKpis(source, elId, currency) {
  try {
    const k = await apiGet(`/api/kpis?source=${source}`);
    const cards = [
      { label: "Total Revenue", value: fmtBRL(k.total_revenue), sub: "delivered" },
      { label: "Total Orders", value: fmtNum(k.total_orders), sub: "all time" },
      { label: "Avg Order Value", value: "R$" + Number(k.avg_order_value).toFixed(0), sub: "per order" },
      { label: "Delivery Rate", value: Number(k.delivery_rate_pct).toFixed(1) + "%", sub: "fulfilment" },
    ];
    document.getElementById(elId).innerHTML = cards
      .map((c) => `<div class="kpi"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub">${c.sub}</div></div>`)
      .join("");
  } catch (e) { showError(elId, "Could not load KPIs."); }
}

function lineChart(canvasId, rows) {
  const box = document.getElementById(canvasId).parentElement;
  if (typeof Chart === "undefined") {
    box.innerHTML = '<table style="width:100%;font-size:13px">' +
      rows.map((r) => `<tr><td style="padding:6px 0;color:#8b8f9a">${r.month}</td><td style="padding:6px 0;text-align:right">${fmtBRL(r.revenue)}</td></tr>`).join("") + "</table>";
    return;
  }
  new Chart(document.getElementById(canvasId), {
    type: "line",
    data: { labels: rows.map((r) => r.month), datasets: [{ data: rows.map((r) => Number(r.revenue)), borderColor: "#e8a33d", backgroundColor: "rgba(232,163,61,0.12)", fill: true, tension: 0.32, pointRadius: 1, borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono", size: 9 }, maxTicksLimit: 12 } },
                y: { grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" }, callback: (v) => "R$" + (v/1000).toFixed(0) + "k" } } } },
  });
}
async function loadRevenue(source, canvasId) {
  try { lineChart(canvasId, await apiGet(`/api/revenue/monthly?source=${source}`)); }
  catch (e) { document.getElementById(canvasId).parentElement.innerHTML = `<div class="error">Could not load revenue. ${e.message}</div>`; }
}

async function loadFunnel(source, elId) {
  try {
    const f = await apiGet(`/api/funnel?source=${source}`);
    const steps = [["Purchased", f.purchased], ["Approved", f.approved], ["Shipped", f.shipped], ["Delivered", f.delivered]];
    const max = steps[0][1] || 1;
    document.getElementById(elId).innerHTML = steps.map(([n, c]) =>
      `<div class="funnel-step"><span class="name">${n}</span><div class="bar-track"><div class="bar-fill" data-w="${100*c/max}"></div></div><span class="count">${fmtNum(c)}</span></div>`).join("");
    requestAnimationFrame(() => document.querySelectorAll(`#${elId} .bar-fill`).forEach((el) => el.style.width = el.dataset.w + "%"));
  } catch (e) { showError(elId, "Could not load funnel."); }
}

async function loadMap(source, mapId, legendId) {
  try { renderMap(mapId, legendId, await apiGet(`/api/revenue-by-state?source=${source}`)); }
  catch (e) { document.getElementById(mapId).innerHTML = `<div class="error">Could not load map. ${e.message}</div>`; }
}

async function loadDelivery(source, elId) {
  try {
    const d = await apiGet(`/api/delivery-performance?source=${source}`);
    document.getElementById(elId).innerHTML =
      `<div class="metric-row"><span class="m-label">Delivered orders</span><span class="m-val">${fmtNum(d.delivered_orders)}</span></div>` +
      `<div class="metric-row"><span class="m-label">Avg delivery time</span><span class="m-val">${d.avg_delivery_days} days</span></div>` +
      `<div class="metric-row"><span class="m-label">Late orders</span><span class="m-val">${fmtNum(d.late_orders)}</span></div>` +
      `<div class="metric-row"><span class="m-label">Late rate</span><span class="m-val">${d.late_rate_pct}%</span></div>`;
  } catch (e) { showError(elId, "Could not load delivery."); }
}

async function loadReview(source, canvasId) {
  try {
    const rows = await apiGet(`/api/review-analysis?source=${source}`);
    const box = document.getElementById(canvasId).parentElement;
    if (typeof Chart === "undefined") {
      box.innerHTML = '<table style="width:100%;font-size:13px">' +
        rows.map((r) => `<tr><td style="padding:6px 0;color:#8b8f9a">${r.review_score}&#9733;</td><td style="padding:6px 0;text-align:right">${fmtNum(r.reviews)}</td><td style="padding:6px 0;text-align:right;color:#8b8f9a">${r.pct_late}% late</td></tr>`).join("") + "</table>";
      return;
    }
    new Chart(document.getElementById(canvasId), {
      type: "bar",
      data: { labels: rows.map((r) => r.review_score + "\u2605"),
        datasets: [
          { label: "Reviews", data: rows.map((r) => Number(r.reviews)), backgroundColor: "rgba(232,163,61,0.55)", borderColor: "#e8a33d", borderWidth: 1, yAxisID: "y", borderRadius: 4 },
          { label: "% late", data: rows.map((r) => Number(r.pct_late)), type: "line", borderColor: "#eb6f6f", backgroundColor: "#eb6f6f", yAxisID: "y1", tension: 0.3, pointRadius: 3 },
        ] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#8b8f9a", font: { family: "JetBrains Mono", size: 10 } } } },
        scales: { x: { grid: { display: false }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" } } },
          y: { position: "left", grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono", size: 9 } } },
          y1: { position: "right", grid: { display: false }, ticks: { color: "#eb6f6f", font: { family: "JetBrains Mono", size: 9 }, callback: (v) => v + "%" } } } },
    });
  } catch (e) { document.getElementById(canvasId).parentElement.innerHTML = `<div class="error">Could not load reviews. ${e.message}</div>`; }
}

async function loadCohort(elId) {
  try {
    const data = await apiGet("/api/cohort-retention?source=olist");
    const heatColor = (v) => v == null ? "var(--panel-2)" : `rgba(232,163,61,${(0.08 + Math.min(1, v/100) * 0.92).toFixed(2)})`;
    const headers = '<th class="cohort-h">Cohort</th>' + Array.from({ length: data.max_offset + 1 }, (_, i) => `<th>M${i}</th>`).join("");
    const body = data.rows.map((row) => {
      const cells = row.cells.map((v) => {
        const txt = v == null ? "" : v + "%";
        const dark = v != null && v / 100 > 0.5;
        return `<td><div class="cell" style="background:${heatColor(v)};color:${dark ? "#1a1205" : "var(--ink)"}">${txt}</div></td>`;
      }).join("");
      return `<tr><td class="cohort-label">${row.cohort} <span style="opacity:.6">(${row.size})</span></td>${cells}</tr>`;
    }).join("");
    document.getElementById(elId).innerHTML = `<table class="heat"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;
  } catch (e) { showError(elId, "Could not load cohorts."); }
}

async function loadSellers(elId) {
  try {
    const rows = await apiGet("/api/sellers/top?limit=10&source=olist");
    const trs = rows.map((s, i) =>
      `<tr><td class="rank">#${i+1}</td><td class="sid">${String(s.seller_id).slice(0,8)}...</td><td><span class="state-tag">${s.seller_state || "-"}</span></td><td class="num">${fmtNum(s.total_orders)}</td><td class="num">${fmtBRL(s.total_revenue)}</td><td class="num">${Number(s.avg_review_score).toFixed(2)}&#9733;</td></tr>`).join("");
    document.getElementById(elId).innerHTML = `<table class="seller-table"><thead><tr><th>Rank</th><th>Seller</th><th>State</th><th class="num">Orders</th><th class="num">Revenue</th><th class="num">Avg Review</th></tr></thead><tbody>${trs}</tbody></table>`;
  } catch (e) { showError(elId, "Could not load sellers."); }
}

async function loadLtv(canvasId) {
  try {
    const rows = await apiGet("/api/customer-segments?source=olist");
    const box = document.getElementById(canvasId).parentElement;
    if (typeof Chart === "undefined") {
      box.innerHTML = '<table style="width:100%;font-size:13px">' + rows.map((r) => `<tr><td style="padding:6px 0;color:#8b8f9a">RFM ${r.rfm_total}</td><td style="padding:6px 0;text-align:right">${fmtNum(r.customers)}</td></tr>`).join("") + "</table>";
      return;
    }
    new Chart(document.getElementById(canvasId), {
      type: "bar",
      data: { labels: rows.map((r) => "RFM " + r.rfm_total), datasets: [{ data: rows.map((r) => Number(r.customers)), backgroundColor: "rgba(232,163,61,0.55)", borderColor: "#e8a33d", borderWidth: 1, borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono", size: 9 } } }, y: { grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" } } } } },
    });
  } catch (e) { document.getElementById(canvasId).parentElement.innerHTML = `<div class="error">Could not load segments. ${e.message}</div>`; }
}

async function loadAbTests(elId) {
  try {
    const exps = await apiGet("/api/ab-tests");
    document.getElementById(elId).innerHTML = exps.map((exp) => {
      const a = exp.variant_a || {}, b = exp.variant_b || {};
      const lift = exp.aov_lift_pct;
      const liftCls = lift > 0 ? "up" : lift < 0 ? "down" : "";
      const liftTxt = lift == null ? "-" : (lift > 0 ? "+" : "") + lift + "%";
      return `<div class="ab-card"><h3>${exp.experiment.replace(/_/g, " ")}</h3>` +
        `<div class="variant-row"><span class="variant-tag">Variant A</span><span>R$${Number(a.avg_order_value||0).toFixed(0)} &middot; ${fmtNum(a.orders||0)} orders</span></div>` +
        `<div class="variant-row"><span class="variant-tag">Variant B</span><span>R$${Number(b.avg_order_value||0).toFixed(0)} &middot; ${fmtNum(b.orders||0)} orders</span></div>` +
        `<div class="lift"><span>AOV lift (B vs A)</span><span class="${liftCls}">${liftTxt}</span></div></div>`;
    }).join("");
  } catch (e) { showError(elId, "Could not load experiments."); }
}

let liveLoaded = false;
function loadRealTab() {
  loadKpis("olist", "kpi-real");
  loadRevenue("olist", "rev-real");
  loadMap("olist", "map-real", "legend-real");
  loadFunnel("olist", "funnel-real");
  loadDelivery("olist", "delivery-real");
  loadReview("olist", "review-real");
  loadCohort("cohort-real");
  loadSellers("sellers-real");
  loadLtv("ltv-real");
}
function loadLiveTab() {
  if (liveLoaded) { Object.values(maps).forEach((m) => setTimeout(() => m.invalidateSize(), 100)); return; }
  liveLoaded = true;
  loadKpis("faker_live", "kpi-live");
  loadRevenue("faker_live", "rev-live");
  loadAbTests("ab-live");
  loadFunnel("faker_live", "funnel-live");
  loadMap("faker_live", "map-live", "legend-live");
  setTimeout(attachLiveInterpretations, 1500);
}

function initTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      document.getElementById("panel-" + tab).classList.add("active");
      if (tab === "live") loadLiveTab();
      else if (tab === "health") loadHealthTab();
      else if (tab === "real") loadRealTabOnce();
      else Object.values(maps).forEach((m) => setTimeout(() => m.invalidateSize(), 100));
    });
  });
}

let interpretationsCache = null;
async function loadInterpretations() {
  try {
    interpretationsCache = await apiGet("/api/interpretations");
  } catch (e) {
    interpretationsCache = {};
  }
}

// Render the AI interpretation block for a chart key into a target panel.
function renderInterpretation(key, panelEl) {
  if (!interpretationsCache || !panelEl) return;
  const data = interpretationsCache[key];
  if (!data || !data.claims || !data.claims.length) return;
  const s = data.summary || {};
  const items = data.claims
    .map((c) => {
      const cls = c.verified ? "claim-ok" : "claim-flag";
      const tag = c.verified ? "verified" : "unverified";
      return `<li><span class="claim-badge ${cls}">${tag}</span><span>${c.text}</span></li>`;
    })
    .join("");
  const block = document.createElement("div");
  block.className = "interp";
  block.innerHTML =
    `<div class="interp-head"><span class="ai-tag">AI interpretation</span>` +
    `<span class="verify-summary">${s.verified_claims || 0}/${s.total_claims || 0} claims NLI-verified</span></div>` +
    `<ul>${items}</ul>`;
  panelEl.appendChild(block);
}

function attachRealInterpretations() {
  renderInterpretation("real:revenue", document.getElementById("rev-real")?.closest(".panel"));
  renderInterpretation("real:state", document.getElementById("map-real")?.closest(".panel"));
  renderInterpretation("real:funnel", document.getElementById("funnel-real")?.closest(".panel"));
  renderInterpretation("real:delivery", document.getElementById("delivery-real")?.closest(".panel"));
  renderInterpretation("real:review", document.getElementById("review-real")?.closest(".panel"));
}
function attachLiveInterpretations() {
  renderInterpretation("live:revenue", document.getElementById("rev-live")?.closest(".panel"));
  renderInterpretation("live:ab", document.getElementById("ab-live")?.closest(".section"));
  renderInterpretation("live:funnel", document.getElementById("funnel-live")?.closest(".panel"));
  renderInterpretation("live:state", document.getElementById("map-live")?.closest(".panel"));
}

let healthLoaded = false;
async function loadHealthTab() {
  if (healthLoaded) return;
  healthLoaded = true;
  try {
    const m = await apiGet("/api/monitoring");
    renderSlis(m);
    renderDrift(m);
    renderModelMetrics(m);
  } catch (e) {
    showError("slis", "Monitoring report unavailable. Run the monitoring job and redeploy.");
    document.getElementById("drift").innerHTML = "";
    document.getElementById("model-metrics").innerHTML = "";
  }
}

function renderSlis(m) {
  const slis = m.slis || [];
  const cards = slis.map((s) => {
    const cls = s.met ? "met" : "breached";
    const badge = s.met ? "status-met" : "status-breached";
    const name = s.name.replace(/_/g, " ");
    return `<div class="sli-card ${cls}"><span class="sli-status ${badge}">${s.met ? "met" : "breached"}</span>` +
      `<div class="sli-name">${name}</div><div class="sli-value">${s.value}${s.unit}</div>` +
      `<div class="sli-obj">SLO: ${s.objective}</div></div>`;
  }).join("");
  const summary = `<div class="note" style="margin-bottom:16px">${m.slo_met}/${m.slo_total} objectives met.</div>`;
  document.getElementById("slis").innerHTML = summary + `<div class="sli-grid">${cards}</div>`;
}

function renderDrift(m) {
  const d = m.drift || {};
  const feats = d.features || [];
  const maxPsi = Math.max(...feats.map((f) => f.psi), 0.3);
  const rows = feats.map((f) => {
    const w = Math.min(100, (f.psi / maxPsi) * 100);
    const bandCls = "psi-" + f.psi_band;
    const badgeCls = f.drifted ? "claim-flag" : "claim-ok";
    return `<div class="drift-row"><span class="dfeat">${f.feature}</span>` +
      `<div class="psi-track"><div class="psi-fill ${bandCls}" style="width:${w}%"></div></div>` +
      `<span class="dks">PSI ${f.psi} &middot; KS ${f.ks_statistic}</span>` +
      `<span class="drift-badge ${badgeCls}">${f.psi_band}</span></div>`;
  }).join("");
  const head = `<div class="note" style="margin-bottom:6px">${d.reference} (reference) vs ${d.current} (current) &middot; ${d.drifted_count}/${d.total_features} features drifted</div>`;
  document.getElementById("drift").innerHTML = head + rows;
}

function renderModelMetrics(m) {
  const models = m.models || {};
  const rows = Object.entries(models).map(([name, met]) => {
    const pairs = Object.entries(met).filter(([k]) => !["trained_at", "status", "error"].includes(k));
    const cells = pairs.map(([k, v]) => `<span style="color:var(--muted)">${k.replace(/_/g, " ")}:</span> ${v}`).join("  &middot;  ");
    return `<div class="metric-row"><span class="m-label">${name}</span><span class="m-val" style="font-size:12px">${cells || met.status || "-"}</span></div>`;
  }).join("");
  document.getElementById("model-metrics").innerHTML = rows || '<div class="note">No model metrics available.</div>';
}

let realLoaded = false;
function loadRealTabOnce() {
  if (realLoaded) {
    Object.values(maps).forEach((m) => setTimeout(() => m.invalidateSize(), 100));
    return;
  }
  realLoaded = true;
  loadRealTab();
  setTimeout(attachRealInterpretations, 1500);
}

async function init() {
  document.getElementById("last-updated").textContent = "\u25CF Loaded " + new Date().toLocaleDateString("pt-BR");
  initTabs();
  await loadInterpretations();
  loadLiveTab();
}
document.addEventListener("DOMContentLoaded", init);
