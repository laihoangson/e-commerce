r"""
pipeline/validate_all.py
========================
Great Expectations 1.x validation for Bronze, Silver, Gold layers.
Uses GE 1.17+ fluent API: ephemeral context + Validator.

Usage (PowerShell):
  cd C:\Users\Admin\Documents\e-commerce
  python pipeline/validate_all.py
  python pipeline/validate_all.py --layer bronze
  python pipeline/validate_all.py --layer silver
  python pipeline/validate_all.py --layer gold

Output:
  - Console: colored pass/fail per expectation
  - reports/validation_TIMESTAMP.html
"""

import os, sys, json, argparse, warnings
import duckdb, pandas as pd
import great_expectations as gx

from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

warnings.filterwarnings("ignore")   # suppress GE progress bars / deprecation noise

load_dotenv()

DB_PATH     = Path(os.getenv("DUCKDB_PATH", "data/ecom.duckdb"))
REPORTS_DIR = Path("reports")
TIMESTAMP   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

GREEN  = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; BOLD = "\033[1m"; RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}+{RESET}  {msg}")
def fail(msg): print(f"  {RED}x{RESET}  {msg}")
def info(msg): print(f"  {CYAN}>{RESET}  {msg}")


# ── Result store ──────────────────────────────────────────────────────────────
class Report:
    def __init__(self): self.rows = []

    def add(self, layer, table, exp, success, details=""):
        self.rows.append(dict(layer=layer, table=table,
                              exp=exp, success=success, details=details))
        (ok if success else fail)(f"[{table}] {exp}" +
                                   (f"  ({details})" if details and not success else ""))

    @property
    def passed(self): return sum(1 for r in self.rows if r["success"])
    @property
    def failed(self): return sum(1 for r in self.rows if not r["success"])
    @property
    def total(self):  return len(self.rows)

    def save_html(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        rows_html = ""
        for r in self.rows:
            c = "#3fb950" if r["success"] else "#f85149"
            icon = "PASS" if r["success"] else "FAIL"
            det  = f" — {r['details']}" if r["details"] and not r["success"] else ""
            rows_html += (f"<tr><td>{r['layer'].upper()}</td>"
                          f"<td><code>{r['table']}</code></td>"
                          f"<td>{r['exp']}{det}</td>"
                          f"<td style='color:{c};font-weight:700'>{icon}</td></tr>\n")
        pct = round(self.passed / self.total * 100) if self.total else 0
        pc  = "#3fb950" if pct == 100 else "#f85149"
        html = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'>
<title>GE Validation {TIMESTAMP}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:32px}}
h1{{color:#f0883e}} .kpis{{display:flex;gap:16px;margin:16px 0 28px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 20px}}
.kv{{font-size:28px;font-weight:700;font-family:monospace}}
.g{{color:#3fb950}} .r{{color:#f85149}} .b{{color:#58a6ff}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #30363d}}
th{{background:#1c2128;color:#8b949e}} tr:hover td{{background:#1c2128}}
code{{background:#1c2128;padding:2px 6px;border-radius:4px;font-size:12px}}
</style></head><body>
<h1>Great Expectations — Validation Report</h1>
<p style='color:#8b949e'>Run: {TIMESTAMP} | DuckDB: {DB_PATH}</p>
<div class='kpis'>
  <div class='kpi'><div style='color:#8b949e;font-size:11px'>PASSED</div>
    <div class='kv g'>{self.passed}</div></div>
  <div class='kpi'><div style='color:#8b949e;font-size:11px'>FAILED</div>
    <div class='kv r'>{self.failed}</div></div>
  <div class='kpi'><div style='color:#8b949e;font-size:11px'>TOTAL</div>
    <div class='kv b'>{self.total}</div></div>
  <div class='kpi'><div style='color:#8b949e;font-size:11px'>PASS RATE</div>
    <div class='kv' style='color:{pc}'>{pct}%</div></div>
</div>
<table><thead><tr><th>Layer</th><th>Table</th>
<th>Expectation</th><th>Result</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""
        path.write_text(html, encoding="utf-8")


# ── Core helper ───────────────────────────────────────────────────────────────
def make_validator(ctx, df: pd.DataFrame, src_name: str) -> "gx.validator.validator.Validator":
    """Create a fresh GE Validator for a DataFrame.
    Handles both ctx.sources (GE 1.x server build) and
    ctx.data_sources (GE 1.x Windows build) APIs.
    """
    # Detect which API is available on this GE build
    factory = getattr(ctx, "sources", None) or getattr(ctx, "data_sources", None)
    if factory is None:
        raise RuntimeError(
            "Cannot find GE datasource factory. "
            "Expected ctx.sources or ctx.data_sources."
        )
    try:
        ds = factory.add_pandas(src_name)
    except Exception:
        # Source name already registered — delete and re-add
        try:
            factory.delete(src_name)
        except Exception:
            pass
        ds = factory.add_pandas(src_name)
    da = ds.add_dataframe_asset("asset")
    # Windows GE build: dataframe passed via options dict, not as direct kwarg
    try:
        br = da.build_batch_request(dataframe=df)
    except TypeError:
        br = da.build_batch_request(options={"dataframe": df})
    return ctx.get_validator(batch_request=br)


def chk(report: Report, layer: str, table: str, v, method: str, **kwargs):
    """Run one expectation on validator v, record result."""
    try:
        res = getattr(v, method)(**kwargs)
        rc  = res.result
        uc  = rc.get("unexpected_count", "")
        up  = rc.get("unexpected_percent", "")
        det = f"{uc} failures ({up:.1f}%)" if uc != "" and not res.success else ""
        report.add(layer, table,
                   f"{method}({', '.join(f'{k}={v2}' for k,v2 in kwargs.items())})",
                   res.success, det)
    except Exception as e:
        report.add(layer, table, f"{method}(...)", False, str(e)[:80])


# ══════════════════════════════════════════════════════════════════════════════
# BRONZE
# ══════════════════════════════════════════════════════════════════════════════
def validate_bronze(con, ctx, report: Report):
    print(f"\n{BOLD}{CYAN}-- BRONZE ------------------------------------------{RESET}")

    # bronze_orders
    info("bronze_orders")
    df = con.execute("SELECT * FROM bronze_orders").df()
    v  = make_validator(ctx, df, "bron_orders")
    chk(report, "bronze", "bronze_orders", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "bronze", "bronze_orders", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "bronze", "bronze_orders", v, "expect_column_values_to_be_unique", column="order_id")
    chk(report, "bronze", "bronze_orders", v, "expect_column_values_to_not_be_null", column="customer_id")
    chk(report, "bronze", "bronze_orders", v, "expect_column_values_to_be_in_set",
        column="order_status",
        value_set=["delivered","shipped","canceled","invoiced",
                   "processing","approved","unavailable","created"])
    chk(report, "bronze", "bronze_orders", v, "expect_column_values_to_not_be_null", column="order_purchase_timestamp")
    chk(report, "bronze", "bronze_orders", v, "expect_column_to_exist", column="_ingested_at")
    chk(report, "bronze", "bronze_orders", v, "expect_column_to_exist", column="_batch_id")

    # bronze_customers
    info("bronze_customers")
    df = con.execute("SELECT * FROM bronze_customers").df()
    v  = make_validator(ctx, df, "bron_customers")
    chk(report, "bronze", "bronze_customers", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "bronze", "bronze_customers", v, "expect_column_values_to_be_unique", column="customer_id")
    chk(report, "bronze", "bronze_customers", v, "expect_column_values_to_not_be_null", column="customer_unique_id")
    chk(report, "bronze", "bronze_customers", v, "expect_column_values_to_not_be_null", column="customer_state")
    chk(report, "bronze", "bronze_customers", v, "expect_column_value_lengths_to_equal", column="customer_state", value=2)

    # bronze_order_items
    info("bronze_order_items")
    df = con.execute("SELECT * FROM bronze_order_items").df()
    v  = make_validator(ctx, df, "bron_items")
    chk(report, "bronze", "bronze_order_items", v, "expect_table_row_count_to_be_between", min_value=100000, max_value=150000)
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_not_be_null", column="product_id")
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_not_be_null", column="seller_id")
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_be_between", column="price", min_value=0.01, max_value=10000)
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_be_between", column="freight_value", min_value=0, max_value=500)
    chk(report, "bronze", "bronze_order_items", v, "expect_column_values_to_be_between", column="order_item_id", min_value=1, max_value=21)

    # bronze_reviews
    info("bronze_reviews")
    df = con.execute("SELECT * FROM bronze_reviews").df()
    v  = make_validator(ctx, df, "bron_reviews")
    chk(report, "bronze", "bronze_reviews", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "bronze", "bronze_reviews", v, "expect_column_values_to_not_be_null", column="review_id")
    chk(report, "bronze", "bronze_reviews", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "bronze", "bronze_reviews", v, "expect_column_values_to_be_between", column="review_score", min_value=1, max_value=5)

    # bronze_products
    info("bronze_products")
    df = con.execute("SELECT * FROM bronze_products").df()
    v  = make_validator(ctx, df, "bron_products")
    chk(report, "bronze", "bronze_products", v, "expect_table_row_count_to_be_between", min_value=30000, max_value=40000)
    chk(report, "bronze", "bronze_products", v, "expect_column_values_to_be_unique", column="product_id")
    chk(report, "bronze", "bronze_products", v, "expect_column_values_to_not_be_null", column="product_id")

    # bronze_sellers
    info("bronze_sellers")
    df = con.execute("SELECT * FROM bronze_sellers").df()
    v  = make_validator(ctx, df, "bron_sellers")
    chk(report, "bronze", "bronze_sellers", v, "expect_table_row_count_to_be_between", min_value=2000, max_value=5000)
    chk(report, "bronze", "bronze_sellers", v, "expect_column_values_to_be_unique", column="seller_id")
    chk(report, "bronze", "bronze_sellers", v, "expect_column_values_to_not_be_null", column="seller_state")
    chk(report, "bronze", "bronze_sellers", v, "expect_column_value_lengths_to_equal", column="seller_state", value=2)

    # bronze_payments
    info("bronze_payments")
    df = con.execute("SELECT * FROM bronze_payments").df()
    v  = make_validator(ctx, df, "bron_payments")
    chk(report, "bronze", "bronze_payments", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "bronze", "bronze_payments", v, "expect_column_values_to_be_in_set",
        column="payment_type",
        value_set=["credit_card","boleto","voucher","debit_card","not_defined"])
    chk(report, "bronze", "bronze_payments", v, "expect_column_values_to_be_between", column="payment_value", min_value=0, max_value=15000)
    chk(report, "bronze", "bronze_payments", v, "expect_column_values_to_be_between", column="payment_installments", min_value=0, max_value=24)

    # bronze_geolocation
    info("bronze_geolocation")
    df = con.execute("SELECT * FROM bronze_geolocation").df()
    v  = make_validator(ctx, df, "bron_geo")
    chk(report, "bronze", "bronze_geolocation", v, "expect_table_row_count_to_be_between", min_value=1000, max_value=30000)
    chk(report, "bronze", "bronze_geolocation", v, "expect_column_values_to_be_between", column="geolocation_lat", min_value=-35, max_value=6, mostly=0.99)
    chk(report, "bronze", "bronze_geolocation", v, "expect_column_values_to_be_between", column="geolocation_lng", min_value=-75, max_value=-28, mostly=0.99)

    # bronze_category_xlat
    info("bronze_category_xlat")
    df = con.execute("SELECT * FROM bronze_category_xlat").df()
    v  = make_validator(ctx, df, "bron_xlat")
    chk(report, "bronze", "bronze_category_xlat", v, "expect_table_row_count_to_be_between", min_value=60, max_value=80)
    chk(report, "bronze", "bronze_category_xlat", v, "expect_column_values_to_not_be_null", column="product_category_name_english")


# ══════════════════════════════════════════════════════════════════════════════
# SILVER
# ══════════════════════════════════════════════════════════════════════════════
def validate_silver(con, ctx, report: Report):
    print(f"\n{BOLD}{CYAN}-- SILVER ------------------------------------------{RESET}")

    # stg_orders
    info("stg_orders")
    df = con.execute("SELECT * FROM main_silver.stg_orders").df()
    v  = make_validator(ctx, df, "silv_orders")
    chk(report, "silver", "stg_orders", v, "expect_table_row_count_to_be_between", min_value=80000, max_value=110000)
    chk(report, "silver", "stg_orders", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "silver", "stg_orders", v, "expect_column_values_to_be_unique", column="order_id")
    chk(report, "silver", "stg_orders", v, "expect_column_to_exist", column="is_on_time")
    chk(report, "silver", "stg_orders", v, "expect_column_to_exist", column="days_late")
    chk(report, "silver", "stg_orders", v, "expect_column_values_to_be_in_set",
        column="is_on_time", value_set=[True, False])
    chk(report, "silver", "stg_orders", v, "expect_column_pair_values_A_to_be_greater_than_B",
        column_A="delivered_at", column_B="purchased_at",
        or_equal=False, ignore_row_if="either_value_is_missing")

    # stg_order_items
    info("stg_order_items")
    df = con.execute("SELECT * FROM main_silver.stg_order_items").df()
    v  = make_validator(ctx, df, "silv_items")
    chk(report, "silver", "stg_order_items", v, "expect_table_row_count_to_be_between", min_value=100000, max_value=150000)
    chk(report, "silver", "stg_order_items", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "silver", "stg_order_items", v, "expect_column_values_to_not_be_null", column="category_en")
    chk(report, "silver", "stg_order_items", v, "expect_column_values_to_be_between", column="price", min_value=0.01, max_value=10000)
    chk(report, "silver", "stg_order_items", v, "expect_column_values_to_be_between", column="total_item_value", min_value=0.01, max_value=11000)
    chk(report, "silver", "stg_order_items", v, "expect_column_values_to_not_be_null", column="seller_state")

    # stg_reviews
    info("stg_reviews")
    df = con.execute("SELECT * FROM main_silver.stg_reviews").df()
    v  = make_validator(ctx, df, "silv_reviews")
    chk(report, "silver", "stg_reviews", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "silver", "stg_reviews", v, "expect_column_values_to_not_be_null", column="review_id")
    chk(report, "silver", "stg_reviews", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "silver", "stg_reviews", v, "expect_column_values_to_be_between", column="review_score", min_value=1, max_value=5)
    chk(report, "silver", "stg_reviews", v, "expect_column_values_to_be_between", column="sentiment_proxy", min_value=-1.0, max_value=1.0)
    chk(report, "silver", "stg_reviews", v, "expect_column_values_to_be_in_set",
        column="sentiment_label", value_set=["positive","neutral","negative"])
    # ml_label lives in mart_voice_of_customer (Gold), not in stg_reviews (Silver)


# ══════════════════════════════════════════════════════════════════════════════
# GOLD
# ══════════════════════════════════════════════════════════════════════════════
def validate_gold(con, ctx, report: Report):
    print(f"\n{BOLD}{CYAN}-- GOLD --------------------------------------------{RESET}")

    # mart_logistics_sla
    info("mart_logistics_sla")
    df = con.execute("SELECT * FROM main_gold.mart_logistics_sla").df()
    v  = make_validator(ctx, df, "gold_sla")
    chk(report, "gold", "mart_logistics_sla", v, "expect_table_row_count_to_be_between", min_value=80000, max_value=110000)
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_be_unique", column="order_id")
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_not_be_null", column="route_id")
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_not_be_null", column="is_on_time")
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_be_between", column="freight_value", min_value=0, max_value=2000)
    chk(report, "gold", "mart_logistics_sla", v, "expect_column_values_to_be_between", column="actual_days", min_value=0, max_value=365)
    otif = df["is_on_time"].mean() * 100
    report.add("gold", "mart_logistics_sla",
               f"otif_rate_between_80_and_100 (actual={otif:.1f}%)",
               80 <= otif <= 100)

    # mart_customer_360
    info("mart_customer_360")
    df = con.execute("SELECT * FROM main_gold.mart_customer_360").df()
    v  = make_validator(ctx, df, "gold_cust")
    chk(report, "gold", "mart_customer_360", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_not_be_null", column="customer_id")
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_unique", column="customer_id")
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_between", column="total_gmv", min_value=0.01, max_value=50000)
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_between", column="r_score", min_value=1, max_value=5)
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_between", column="f_score", min_value=1, max_value=5)
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_between", column="m_score", min_value=1, max_value=5)
    chk(report, "gold", "mart_customer_360", v, "expect_column_values_to_be_between", column="otif_pct", min_value=0, max_value=100)

    # mart_sales_and_demand
    info("mart_sales_and_demand")
    df = con.execute("SELECT * FROM main_gold.mart_sales_and_demand").df()
    v  = make_validator(ctx, df, "gold_demand")
    chk(report, "gold", "mart_sales_and_demand", v, "expect_table_row_count_to_be_between", min_value=100, max_value=5000)
    chk(report, "gold", "mart_sales_and_demand", v, "expect_column_values_to_not_be_null", column="ds")
    chk(report, "gold", "mart_sales_and_demand", v, "expect_column_values_to_not_be_null", column="product_category")
    chk(report, "gold", "mart_sales_and_demand", v, "expect_column_values_to_be_between", column="revenue", min_value=0, max_value=2000000)
    chk(report, "gold", "mart_sales_and_demand", v, "expect_column_values_to_be_between", column="cancellation_rate_pct", min_value=0, max_value=100)
    min_yr = pd.to_datetime(df["ds"]).dt.year.min()
    max_yr = pd.to_datetime(df["ds"]).dt.year.max()
    report.add("gold", "mart_sales_and_demand",
               f"time_series_spans_2016_to_2018 ({min_yr}-{max_yr})",
               int(min_yr) <= 2016 and int(max_yr) >= 2018)

    # mart_product_affinity
    info("mart_product_affinity")
    df = con.execute("SELECT * FROM main_gold.mart_product_affinity").df()
    v  = make_validator(ctx, df, "gold_affinity")
    chk(report, "gold", "mart_product_affinity", v, "expect_table_row_count_to_be_between", min_value=80000, max_value=120000)
    chk(report, "gold", "mart_product_affinity", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "gold", "mart_product_affinity", v, "expect_column_values_to_not_be_null", column="basket")
    chk(report, "gold", "mart_product_affinity", v, "expect_column_values_to_be_between", column="basket_size", min_value=1, max_value=30)
    chk(report, "gold", "mart_product_affinity", v, "expect_column_values_to_be_between", column="basket_value", min_value=0.01, max_value=50000)

    # mart_voice_of_customer
    info("mart_voice_of_customer")
    df = con.execute("SELECT * FROM main_gold.mart_voice_of_customer").df()
    v  = make_validator(ctx, df, "gold_voc")
    chk(report, "gold", "mart_voice_of_customer", v, "expect_table_row_count_to_be_between", min_value=90000, max_value=120000)
    chk(report, "gold", "mart_voice_of_customer", v, "expect_column_values_to_not_be_null", column="review_id")
    chk(report, "gold", "mart_voice_of_customer", v, "expect_column_values_to_not_be_null", column="order_id")
    chk(report, "gold", "mart_voice_of_customer", v, "expect_column_values_to_be_between", column="review_score", min_value=1, max_value=5)
    chk(report, "gold", "mart_voice_of_customer", v, "expect_column_values_to_be_in_set",
        column="sentiment_label", value_set=["positive","neutral","negative"])
    avg = df["review_score"].mean()
    report.add("gold", "mart_voice_of_customer",
               f"avg_review_score_between_3.5_and_5.0 (actual={avg:.2f})",
               3.5 <= avg <= 5.0)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", choices=["bronze","silver","gold"])
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  E-Commerce Intelligence Platform — GE Validation{RESET}")
    print(f"  DuckDB  : {DB_PATH.resolve()}")
    print(f"  GE      : {gx.__version__}")
    print(f"  Layers  : {args.layer or 'bronze + silver + gold'}")
    print(f"{BOLD}{'='*60}{RESET}")

    if not DB_PATH.exists():
        print(f"\n{RED}  DuckDB not found. Run ingest_bronze.py + dbt run first.{RESET}")
        sys.exit(1)

    report = Report()
    ctx    = gx.get_context(mode="ephemeral")

    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        if not args.layer or args.layer == "bronze": validate_bronze(con, ctx, report)
        if not args.layer or args.layer == "silver": validate_silver(con, ctx, report)
        if not args.layer or args.layer == "gold":   validate_gold(con, ctx, report)

    pct = round(report.passed / report.total * 100) if report.total else 0
    col = GREEN if report.failed == 0 else RED
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"  {BOLD}Results:{RESET}  {GREEN}{report.passed} passed{RESET}  "
          f"{col}{report.failed} failed{RESET}  ({pct}% of {report.total})")

    html_path = REPORTS_DIR / f"validation_{TIMESTAMP}.html"
    report.save_html(html_path)
    print(f"\n  HTML report: {html_path}")
    print(f"  Open with : start {html_path}\n")

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()