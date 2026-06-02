const API = () => CONFIG.API_BASE.replace(/\/+$/, "");
const charts = {};

const fmtBRL = (n) => "R$" + Number(n || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const fmtNum = (n) => Number(n || 0).toLocaleString("pt-BR");
const fmtPct = (n) => Number(n || 0).toFixed(1) + "%";

async function apiGet(path) {
  const res = await fetch(API() + path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function setLoading(id) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = '<div class="loading">Loading data...</div>';
}

function setError(id, message) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = `<div class="error">${message}<br>Render free tier may need a short wake-up.</div>`;
}

function renderKpis(id, cards) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = cards.map((c) => `
    <article class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub || ""}</div>
    </article>
  `).join("");
}

function renderMetrics(id, rows) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = rows.map((r) => `
    <div class="metric-row">
      <strong>${r.label}</strong>
      <span class="${r.cls || ""}">${r.value}</span>
    </div>
  `).join("");
}

function renderRankList(id, rows, labelKey, valueKey, subKey) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = rows.map((r, i) => `
    <div class="rank-row">
      <div>
        <strong>#${i + 1} ${r[labelKey] || "-"}</strong>
        <span>${subKey ? r[subKey] || "" : ""}</span>
      </div>
      <strong>${valueKey(r)}</strong>
    </div>
  `).join("");
}

function makeLineChart(canvasId, labels, datasets) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === "undefined") return;
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(el, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#68707d", font: { family: "Inter" } } },
      },
      scales: {
        x: { grid: { color: "#e5dfd2" }, ticks: { color: "#68707d", maxTicksLimit: 10 } },
        y: { grid: { color: "#e5dfd2" }, ticks: { color: "#68707d", callback: (v) => "R$" + (v / 1000).toFixed(0) + "k" } },
      },
    },
  });
}

function makeBarChart(canvasId, labels, data, label, color = "#0f766e") {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === "undefined") return;
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(el, {
    type: "bar",
    data: { labels, datasets: [{ label, data, backgroundColor: color, borderRadius: 5 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#68707d" } },
        y: { grid: { color: "#e5dfd2" }, ticks: { color: "#68707d" } },
      },
    },
  });
}

async function loadKpis(source, id, params = "") {
  const k = await apiGet(`/api/kpis?source=${source}${params}`);
  renderKpis(id, [
    { label: "Total Revenue", value: fmtBRL(k.total_revenue), sub: "delivered orders" },
    { label: "Total Orders", value: fmtNum(k.total_orders), sub: "delivered orders" },
    { label: "Average Order Value", value: fmtBRL(k.avg_order_value), sub: "per delivered order" },
    { label: "Delivery Rate", value: fmtPct(k.delivery_rate_pct), sub: "purchase to delivered" },
  ]);
  return k;
}

async function loadOlist() {
  ["olist-kpis", "olist-states", "olist-cohort", "olist-sellers", "olist-delivery"].forEach(setLoading);
  try {
    await loadKpis("olist", "olist-kpis");
    const revenue = await apiGet("/api/revenue/monthly?source=olist");
    makeLineChart("olist-revenue", revenue.map((r) => r.month), [
      {
        label: "Revenue",
        data: revenue.map((r) => Number(r.revenue)),
        borderColor: "#0f766e",
        backgroundColor: "rgba(15, 118, 110, 0.12)",
        fill: true,
        tension: 0.32,
        pointRadius: 1,
      },
    ]);

    const states = await apiGet("/api/revenue-by-state?source=olist");
    renderRankList("olist-states", states.slice(0, 10), "state", (r) => fmtBRL(r.revenue), "orders");

    const cohort = await apiGet("/api/cohort-retention?source=olist");
    renderCohort("olist-cohort", cohort);

    const sellers = await apiGet("/api/sellers/top?source=olist&limit=10");
    renderSellerTable("olist-sellers", sellers);

    const segments = await apiGet("/api/customer-segments?source=olist");
    makeBarChart("olist-rfm", segments.map((r) => "RFM " + r.rfm_total), segments.map((r) => Number(r.customers)), "Customers");

    const delivery = await apiGet("/api/delivery-performance?source=olist");
    renderMetrics("olist-delivery", [
      { label: "Delivered orders", value: fmtNum(delivery.delivered_orders) },
      { label: "Average delivery time", value: `${delivery.avg_delivery_days} days` },
      { label: "Late orders", value: fmtNum(delivery.late_orders), cls: "status-warn" },
      { label: "Late rate", value: fmtPct(delivery.late_rate_pct), cls: "status-warn" },
    ]);

    const reviews = await apiGet("/api/review-analysis?source=olist");
    makeBarChart("olist-reviews", reviews.map((r) => `${r.review_score} star`), reviews.map((r) => Number(r.pct_late)), "% late delivery", "#b7791f");
  } catch (err) {
    ["olist-kpis", "olist-states", "olist-cohort", "olist-sellers", "olist-delivery"].forEach((id) => setError(id, `Could not load Olist data. ${err.message}`));
  }
}

function renderCohort(id, data) {
  const el = document.getElementById(id);
  if (!el) return;
  const headers = Array.from({ length: data.max_offset + 1 }, (_, i) => `<th>M${i}</th>`).join("");
  const rows = data.rows.slice(0, 18).map((row) => {
    const cells = row.cells.map((v) => `<td class="heat-cell">${v == null ? "" : v + "%"}</td>`).join("");
    return `<tr><td>${row.cohort}<br><span>${fmtNum(row.size)} customers</span></td>${cells}</tr>`;
  }).join("");
  el.innerHTML = `<table><thead><tr><th>Cohort</th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderSellerTable(id, rows) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <table>
      <thead><tr><th>Seller</th><th>State</th><th>Orders</th><th>Revenue</th><th>Review</th></tr></thead>
      <tbody>
        ${rows.map((s) => `
          <tr>
            <td>${String(s.seller_id).slice(0, 8)}...</td>
            <td>${s.seller_state || "-"}</td>
            <td>${fmtNum(s.total_orders)}</td>
            <td>${fmtBRL(s.total_revenue)}</td>
            <td>${Number(s.avg_review_score || 0).toFixed(2)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

async function loadSynthetic(event) {
  if (event) event.preventDefault();
  ["synthetic-kpis", "synthetic-risk", "synthetic-ab", "synthetic-reactivation", "synthetic-recs", "synthetic-forecast", "synthetic-trust", "synthetic-drift"].forEach(setLoading);

  const period = document.getElementById("period-select")?.value || "month";
  const start = document.getElementById("start-date")?.value || "2024-01-01";
  const end = document.getElementById("end-date")?.value || "2026-05-25";
  const params = `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
  const periodLabel = { day: "Daily", week: "Weekly", month: "Monthly", year: "Yearly" }[period] || "Monthly";
  const label = document.getElementById("synthetic-period-label");
  if (label) label.textContent = periodLabel;

  try {
    await loadKpis("faker_live", "synthetic-kpis", params);
    const series = await apiGet(`/api/revenue/timeseries?source=faker_live&period=${period}${params}`);
    makeSyntheticTrend(series);
    renderSyntheticRisk(series);
    await Promise.all([
      loadExperiments(),
      loadMlPanels(),
      loadMonitoring(),
    ]);
  } catch (err) {
    ["synthetic-kpis", "synthetic-risk", "synthetic-ab", "synthetic-reactivation", "synthetic-recs", "synthetic-forecast", "synthetic-trust", "synthetic-drift"].forEach((id) => setError(id, `Could not load synthetic data. ${err.message}`));
  }
}

function makeSyntheticTrend(rows) {
  const labels = rows.map((r) => r.period);
  const revenue = rows.map((r) => Number(r.revenue));
  const ma = movingAverage(revenue, Math.min(4, Math.max(2, Math.floor(revenue.length / 8))));
  makeLineChart("synthetic-revenue", labels, [
    {
      label: "Revenue",
      data: revenue,
      borderColor: "#0f766e",
      backgroundColor: "rgba(15, 118, 110, 0.12)",
      fill: true,
      tension: 0.28,
      pointRadius: 1,
    },
    {
      label: "Moving average",
      data: ma,
      borderColor: "#b7791f",
      backgroundColor: "transparent",
      borderDash: [6, 6],
      tension: 0.22,
      pointRadius: 0,
    },
  ]);
}

function movingAverage(values, windowSize) {
  return values.map((_, i) => {
    const start = Math.max(0, i - windowSize + 1);
    const slice = values.slice(start, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

function renderSyntheticRisk(rows) {
  const el = document.getElementById("synthetic-risk");
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = '<div class="loading">No data in selected range.</div>';
    return;
  }
  const last = rows[rows.length - 1];
  const prev = rows[rows.length - 2] || last;
  const revChange = pctChange(Number(last.revenue), Number(prev.revenue));
  const orderChange = pctChange(Number(last.orders), Number(prev.orders));
  const forecast = simpleForecast(rows.map((r) => Number(r.revenue)));
  el.innerHTML = [
    insight("Revenue change", `${signed(revChange)} vs previous period`, revChange < -5 ? "status-bad" : revChange > 5 ? "status-good" : "status-warn"),
    insight("Order change", `${signed(orderChange)} vs previous period`, orderChange < -5 ? "status-bad" : orderChange > 5 ? "status-good" : "status-warn"),
    insight("Next-period forecast", fmtBRL(forecast), "status-good"),
    insight("Action", revChange < -5 ? "Check state/seller mix and campaign performance." : "Keep monitoring trend and test lift.", ""),
  ].join("");
}

function insight(label, value, cls) {
  return `<div class="insight-row"><strong>${label}</strong><span class="${cls}">${value}</span></div>`;
}

function pctChange(current, previous) {
  if (!previous) return 0;
  return ((current - previous) / previous) * 100;
}

function signed(n) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function simpleForecast(values) {
  if (!values.length) return 0;
  const recent = values.slice(-4);
  return recent.reduce((a, b) => a + b, 0) / recent.length;
}

async function loadExperiments() {
  try {
    const rows = await apiGet("/api/ab-tests");
    const el = document.getElementById("synthetic-ab");
    if (!el) return;
    el.innerHTML = rows.map((exp) => {
      const lift = Number(exp.aov_lift_pct || 0);
      const decision = lift > 5 ? "Roll out candidate" : Math.abs(lift) < 3 ? "Keep as control / rerun" : "Review sample and cost";
      return `
        <article class="action-card">
          <h3>${exp.experiment.replace(/_/g, " ")}</h3>
          <div class="metric-row"><strong>Variant A AOV</strong><span>${fmtBRL(exp.variant_a?.avg_order_value)}</span></div>
          <div class="metric-row"><strong>Variant B AOV</strong><span>${fmtBRL(exp.variant_b?.avg_order_value)}</span></div>
          <div class="metric-row"><strong>Lift</strong><span class="${lift > 0 ? "status-good" : "status-warn"}">${signed(lift)}</span></div>
          <p class="mini-copy">${decision}</p>
        </article>
      `;
    }).join("");
  } catch (err) {
    setError("synthetic-ab", `Could not load experiments. ${err.message}`);
  }
}

async function loadMlPanels() {
  try {
    const status = await apiGet("/api/ml/status");
    const reactivation = status.reactivation || {};
    const recommendation = status.recommendation || {};
    renderMetrics("synthetic-reactivation", [
      { label: "Purpose", value: "Target customers likely to buy again" },
      { label: "PR-AUC", value: reactivation.pr_auc ?? reactivation.status ?? "Unavailable" },
      { label: "Positive rate", value: reactivation.positive_rate ? fmtPct(reactivation.positive_rate * 100) : "Unavailable" },
    ]);
    renderMetrics("synthetic-recs", [
      { label: "Purpose", value: "Personalize products and fallback to popular items" },
      { label: "Recall@10", value: recommendation.recall_at_10 ?? recommendation.status ?? "Unavailable" },
      { label: "Users", value: recommendation.n_users ? fmtNum(recommendation.n_users) : "Unavailable" },
    ]);
  } catch (err) {
    renderMetrics("synthetic-reactivation", [{ label: "Purpose", value: "Target customers likely to buy again" }, { label: "Status", value: "Model artifact unavailable", cls: "status-warn" }]);
    renderMetrics("synthetic-recs", [{ label: "Purpose", value: "Recommend products from purchase history" }, { label: "Status", value: "Model artifact unavailable", cls: "status-warn" }]);
  }
  renderMetrics("synthetic-forecast", [
    { label: "Should use time series?", value: "Yes, for revenue and orders", cls: "status-good" },
    { label: "Best first model", value: "Moving average / exponential smoothing" },
    { label: "Avoid initially", value: "Heavy LSTM-style models" },
  ]);
}

async function loadMonitoring() {
  try {
    const m = await apiGet("/api/monitoring");
    renderMetrics("synthetic-trust", [
      { label: "SLOs met", value: `${m.slo_met}/${m.slo_total}`, cls: m.slo_met === m.slo_total ? "status-good" : "status-warn" },
      ...(m.slis || []).slice(0, 4).map((s) => ({ label: s.name.replace(/_/g, " "), value: `${s.value}${s.unit}`, cls: s.met ? "status-good" : "status-bad" })),
    ]);
    const drift = m.drift?.features || [];
    const el = document.getElementById("synthetic-drift");
    if (el) {
      el.innerHTML = drift.slice(0, 5).map((d) => insight(d.feature, `PSI ${d.psi} / ${d.psi_band}`, d.drifted ? "status-warn" : "status-good")).join("") ||
        '<div class="loading">No drift report available.</div>';
    }
  } catch (err) {
    setError("synthetic-trust", `Monitoring unavailable. ${err.message}`);
    setError("synthetic-drift", `Drift unavailable. ${err.message}`);
  }
}

function init() {
  const page = document.body.dataset.page;
  if (page === "olist") loadOlist();
  if (page === "synthetic") {
    document.getElementById("synthetic-controls")?.addEventListener("submit", loadSynthetic);
    loadSynthetic();
  }
}

document.addEventListener("DOMContentLoaded", init);
