// RetailLens dashboard logic.
//
// Hybrid data sourcing per design:
//   - Computed/aggregate endpoints (KPIs, A/B lift, monthly revenue) -> FastAPI
//   - Simple table reads -> Supabase REST directly
// Falls back gracefully with inline error messages if an endpoint is down
// (e.g. Render cold start on first load).

const fmtMoney = (n) =>
  "R$" + Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const fmtNum = (n) => Number(n).toLocaleString("pt-BR");

async function apiGet(path) {
  const base = CONFIG.API_BASE.replace(/\/+$/, ""); // strip trailing slash(es)
  const res = await fetch(base + path);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

async function restGet(table, query = "") {
  const base = CONFIG.SUPABASE_URL.replace(/\/+$/, "");
  const url = `${base}/rest/v1/${table}?${query}`;
  const res = await fetch(url, {
    headers: {
      apikey: CONFIG.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${CONFIG.SUPABASE_ANON_KEY}`,
    },
  });
  if (!res.ok) throw new Error(`REST ${table} -> ${res.status}`);
  return res.json();
}

function showError(elId, msg) {
  document.getElementById(elId).innerHTML =
    `<div class="error">${msg}<br/>` +
    `Tip: Render free tier sleeps after inactivity — the first request can take ~30–50s. Reload shortly.</div>`;
}

// 1. Overview KPIs (FastAPI: /api/kpis)
async function loadKpis() {
  try {
    const k = await apiGet("/api/kpis");
    const cards = [
      { label: "Total Revenue", value: fmtMoney(k.total_revenue), sub: "delivered orders" },
      { label: "Total Orders", value: fmtNum(k.total_orders), sub: "all time" },
      { label: "Avg Order Value", value: "R$" + Number(k.avg_order_value).toFixed(0), sub: "per order" },
      { label: "Customers", value: fmtNum(k.total_customers), sub: "unique" },
      { label: "Delivery Rate", value: Number(k.delivery_rate_pct).toFixed(1) + "%", sub: "fulfilment" },
    ];
    document.getElementById("kpi-grid").innerHTML = cards
      .map(
        (c) =>
          `<div class="kpi"><div class="label">${c.label}</div>` +
          `<div class="value">${c.value}</div><div class="sub">${c.sub}</div></div>`
      )
      .join("");
  } catch (e) {
    showError("kpi-grid", "Could not load KPIs.");
  }
}

// 2. Monthly revenue (FastAPI: /api/revenue/monthly)
async function loadRevenue() {
  try {
    const rows = await apiGet("/api/revenue/monthly");
    const labels = rows.map((r) => r.month);
    const data = rows.map((r) => Number(r.revenue));

    // Fallback: if Chart.js failed to load (e.g. CDN blocked), show a table.
    if (typeof Chart === "undefined") {
      const box = document.querySelector("#revenue-chart").parentElement;
      box.innerHTML =
        '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
        rows
          .map(
            (r) =>
              `<tr><td style="padding:8px 0;color:#8b8f9a">${r.month}</td>` +
              `<td style="padding:8px 0;text-align:right">R$${Number(r.revenue).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}</td>` +
              `<td style="padding:8px 0;text-align:right;color:#8b8f9a">${r.orders} orders</td></tr>`
          )
          .join("") +
        "</table>";
      return;
    }

    new Chart(document.getElementById("revenue-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Revenue (R$)",
            data,
            borderColor: "#e8a33d",
            backgroundColor: "rgba(232,163,61,0.12)",
            fill: true,
            tension: 0.32,
            pointRadius: 2,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" } } },
          y: {
            grid: { color: "#2a2e37" },
            ticks: {
              color: "#8b8f9a",
              font: { family: "JetBrains Mono" },
              callback: (v) => "R$" + (v / 1000).toFixed(0) + "k",
            },
          },
        },
      },
    });
  } catch (e) {
    document.querySelector("#revenue-chart").parentElement.innerHTML =
      `<div class="error">Could not load revenue. ${e.message}</div>`;
  }
}

// 3. A/B experiments (FastAPI: /api/ab-tests)
async function loadAbTests() {
  try {
    const exps = await apiGet("/api/ab-tests");
    document.getElementById("ab-grid").innerHTML = exps
      .map((exp) => {
        const a = exp.variant_a || {};
        const b = exp.variant_b || {};
        const lift = exp.aov_lift_pct;
        const liftCls = lift > 0 ? "up" : lift < 0 ? "down" : "";
        const liftTxt = lift === null ? "—" : (lift > 0 ? "+" : "") + lift + "%";
        return (
          `<div class="ab-card"><h3>${exp.experiment.replace(/_/g, " ")}</h3>` +
          `<div class="variant-row"><span class="variant-tag">Variant A</span>` +
          `<span class="variant-val">R$${Number(a.avg_order_value || 0).toFixed(0)} AOV · ${fmtNum(a.orders || 0)} orders</span></div>` +
          `<div class="variant-row"><span class="variant-tag">Variant B</span>` +
          `<span class="variant-val">R$${Number(b.avg_order_value || 0).toFixed(0)} AOV · ${fmtNum(b.orders || 0)} orders</span></div>` +
          `<div class="lift"><span>AOV lift (B vs A)</span><span class="${liftCls}">${liftTxt}</span></div></div>`
        );
      })
      .join("");
  } catch (e) {
    showError("ab-grid", "Could not load experiments.");
  }
}

// 4. Funnel (Supabase REST: funnel_conversion)
async function loadFunnel() {
  try {
    const rows = await restGet("funnel_conversion", "limit=1");
    const f = rows[0];
    const steps = [
      { name: "Purchased", count: f.purchased },
      { name: "Approved", count: f.approved },
      { name: "Shipped", count: f.shipped },
      { name: "Delivered", count: f.delivered },
    ];
    const max = steps[0].count || 1;
    document.getElementById("funnel").innerHTML = steps
      .map(
        (s) =>
          `<div class="funnel-step"><span class="name">${s.name}</span>` +
          `<div class="bar-track"><div class="bar-fill" data-w="${(100 * s.count) / max}"></div></div>` +
          `<span class="count">${fmtNum(s.count)}</span></div>`
      )
      .join("");
    // animate bars after layout
    requestAnimationFrame(() => {
      document.querySelectorAll(".bar-fill").forEach((el) => {
        el.style.width = el.dataset.w + "%";
      });
    });
  } catch (e) {
    showError(
      "funnel",
      "Could not load funnel. If this is a Supabase REST error (401/permission), enable read access — see dashboard/README.md."
    );
  }
}

// 5. Cohort retention heatmap (FastAPI: /api/cohort-retention)
function heatColor(pct) {
  if (pct === null || pct === undefined) return "var(--panel-2)";
  // 0% -> faint, 100% -> full accent
  const t = Math.min(1, pct / 100);
  const alpha = 0.08 + t * 0.92;
  return `rgba(232,163,61,${alpha.toFixed(2)})`;
}
async function loadCohort() {
  try {
    const data = await apiGet("/api/cohort-retention");
    const headers =
      '<th class="cohort-h">Cohort</th>' +
      Array.from({ length: data.max_offset + 1 }, (_, i) => `<th>M${i}</th>`).join("");
    const body = data.rows
      .map((row) => {
        const cells = row.cells
          .map((v) => {
            const txt = v === null ? "" : v + "%";
            const dark = v !== null && v / 100 > 0.5;
            return `<td><div class="cell" style="background:${heatColor(v)};color:${dark ? "#1a1205" : "var(--ink)"}">${txt}</div></td>`;
          })
          .join("");
        return `<tr><td class="cohort-label">${row.cohort} <span style="opacity:.6">(${row.size})</span></td>${cells}</tr>`;
      })
      .join("");
    document.getElementById("cohort").innerHTML =
      `<table class="heat"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;
  } catch (e) {
    showError("cohort", "Could not load cohorts.");
  }
}

// 6. Top sellers (FastAPI: /api/sellers/top)
async function loadSellers() {
  try {
    const rows = await apiGet("/api/sellers/top?limit=10");
    const trs = rows
      .map(
        (s, i) =>
          `<tr><td class="rank">#${i + 1}</td>` +
          `<td class="sid">${String(s.seller_id).slice(0, 8)}…</td>` +
          `<td><span class="state-tag">${s.seller_state || "—"}</span></td>` +
          `<td class="num">${fmtNum(s.total_orders)}</td>` +
          `<td class="num">${fmtMoney(s.total_revenue)}</td>` +
          `<td class="num">${Number(s.avg_review_score).toFixed(2)}★</td></tr>`
      )
      .join("");
    document.getElementById("sellers").innerHTML =
      `<table class="seller-table"><thead><tr>` +
      `<th>Rank</th><th>Seller</th><th>State</th>` +
      `<th class="num">Orders</th><th class="num">Revenue</th><th class="num">Avg Review</th>` +
      `</tr></thead><tbody>${trs}</tbody></table>`;
  } catch (e) {
    showError("sellers", "Could not load sellers.");
  }
}

// 7. Customer LTV segments (FastAPI: /api/customer-segments)
async function loadLtv() {
  try {
    const rows = await apiGet("/api/customer-segments");
    const labels = rows.map((r) => "RFM " + r.rfm_total);
    const counts = rows.map((r) => Number(r.customers));
    if (typeof Chart === "undefined") {
      document.querySelector("#ltv-chart").parentElement.innerHTML =
        '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
        rows
          .map(
            (r) =>
              `<tr><td style="padding:8px 0;color:#8b8f9a">RFM ${r.rfm_total}</td>` +
              `<td style="padding:8px 0;text-align:right">${fmtNum(r.customers)} customers</td>` +
              `<td style="padding:8px 0;text-align:right;color:#8b8f9a">R$${Number(r.avg_monetary).toFixed(0)} avg</td></tr>`
          )
          .join("") +
        "</table>";
      return;
    }
    new Chart(document.getElementById("ltv-chart"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Customers",
            data: counts,
            backgroundColor: "rgba(232,163,61,0.55)",
            borderColor: "#e8a33d",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono", size: 10 } } },
          y: { grid: { color: "#2a2e37" }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" } } },
        },
      },
    });
  } catch (e) {
    document.querySelector("#ltv-chart").parentElement.innerHTML =
      `<div class="error">Could not load segments. ${e.message}</div>`;
  }
}

// 8. Delivery performance (FastAPI: /api/delivery-performance)
async function loadDelivery() {
  try {
    const rows = await apiGet("/api/delivery-performance?limit=10");
    const trs = rows
      .map(
        (d) =>
          `<tr><td><span class="state-tag">${d.state}</span></td>` +
          `<td class="num">${fmtNum(d.delivered_orders)}</td>` +
          `<td class="num">${Number(d.avg_delivery_days).toFixed(1)} days</td>` +
          `<td class="num">${Number(d.late_rate_pct).toFixed(1)}%</td></tr>`
      )
      .join("");
    document.getElementById("delivery").innerHTML =
      `<table class="seller-table"><thead><tr>` +
      `<th>State</th><th class="num">Delivered</th>` +
      `<th class="num">Avg Time</th><th class="num">Late Rate</th>` +
      `</tr></thead><tbody>${trs}</tbody></table>`;
  } catch (e) {
    showError("delivery", "Could not load delivery performance.");
  }
}

// 9. Review analysis (FastAPI: /api/review-analysis)
async function loadReview() {
  try {
    const rows = await apiGet("/api/review-analysis");
    const labels = rows.map((r) => r.review_score + "★");
    const lateRates = rows.map((r) => Number(r.late_rate_pct));
    if (typeof Chart === "undefined") {
      document.querySelector("#review-chart").parentElement.innerHTML =
        '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
        '<tr style="color:#8b8f9a"><td>Score</td><td style="text-align:right">Reviews</td><td style="text-align:right">Late rate</td></tr>' +
        rows
          .map(
            (r) =>
              `<tr><td style="padding:6px 0">${r.review_score}★</td>` +
              `<td style="padding:6px 0;text-align:right">${fmtNum(r.reviews)}</td>` +
              `<td style="padding:6px 0;text-align:right;color:#e8a33d">${r.late_rate_pct}%</td></tr>`
          )
          .join("") +
        "</table>";
      return;
    }
    new Chart(document.getElementById("review-chart"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Late delivery rate (%)",
            data: lateRates,
            backgroundColor: "rgba(232,163,61,0.6)",
            borderColor: "#e8a33d",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          title: {
            display: true,
            text: "Lower review scores correlate with late delivery",
            color: "#8b8f9a",
            font: { family: "JetBrains Mono", size: 12 },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" } } },
          y: {
            grid: { color: "#2a2e37" },
            ticks: { color: "#8b8f9a", font: { family: "JetBrains Mono" }, callback: (v) => v + "%" },
          },
        },
      },
    });
  } catch (e) {
    document.querySelector("#review-chart").parentElement.innerHTML =
      `<div class="error">Could not load review analysis. ${e.message}</div>`;
  }
}

function init() {
  document.getElementById("last-updated").textContent =
    "● Loaded " + new Date().toLocaleDateString("pt-BR");
  loadKpis();
  loadRevenue();
  loadAbTests();
  loadFunnel();
  loadCohort();
  loadSellers();
  loadLtv();
  loadDelivery();
  loadReview();
}

document.addEventListener("DOMContentLoaded", init);
