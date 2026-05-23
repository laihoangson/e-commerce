// RetailLens dashboard logic.
//
// Hybrid data sourcing per design:
//   - Computed/aggregate endpoints (KPIs, A/B lift, monthly revenue) -> FastAPI
//   - Simple table reads -> Supabase REST directly
// Falls back gracefully with inline error messages if an endpoint is down
// (e.g. Render cold start on first load).

const fmtMoney = (n) =>
  "A$" + Number(n).toLocaleString("en-AU", { maximumFractionDigits: 0 });
const fmtNum = (n) => Number(n).toLocaleString("en-AU");

async function apiGet(path) {
  const res = await fetch(CONFIG.API_BASE + path);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

async function restGet(table, query = "") {
  const url = `${CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
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
      { label: "Avg Order Value", value: "A$" + Number(k.avg_order_value).toFixed(0), sub: "per order" },
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
              `<td style="padding:8px 0;text-align:right">A$${Number(r.revenue).toLocaleString("en-AU", { maximumFractionDigits: 0 })}</td>` +
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
            label: "Revenue (A$)",
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
              callback: (v) => "A$" + (v / 1000).toFixed(0) + "k",
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
          `<span class="variant-val">A$${Number(a.avg_order_value || 0).toFixed(0)} AOV · ${fmtNum(a.orders || 0)} orders</span></div>` +
          `<div class="variant-row"><span class="variant-tag">Variant B</span>` +
          `<span class="variant-val">A$${Number(b.avg_order_value || 0).toFixed(0)} AOV · ${fmtNum(b.orders || 0)} orders</span></div>` +
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

function init() {
  document.getElementById("last-updated").textContent =
    "● Loaded " + new Date().toLocaleDateString("en-AU");
  loadKpis();
  loadRevenue();
  loadAbTests();
  loadFunnel();
}

document.addEventListener("DOMContentLoaded", init);
