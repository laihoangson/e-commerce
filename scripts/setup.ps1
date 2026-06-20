# scripts/setup.ps1
# Run from repo root: .\scripts\setup.ps1
# Requires Python 3.12.x and pip in PATH

$ErrorActionPreference = "Stop"
Write-Host "`n=== E-Commerce Intelligence Platform — Setup ===" -ForegroundColor Cyan

# 1. Create venv
if (-not (Test-Path ".venv")) {
    Write-Host "`n[1/5] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

# 2. Upgrade pip silently
Write-Host "[2/5] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip -q

# 3. Install dependencies
Write-Host "[3/5] Installing dependencies (this takes ~3 min first time)..." -ForegroundColor Yellow
pip install -r requirements.txt -q

# 4. Copy .env.example → .env if not exists
if (-not (Test-Path ".env")) {
    Write-Host "[4/5] Creating .env from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "  ⚠  Open .env and fill in SUPABASE_URL / SUPABASE_SERVICE_KEY / GROQ_API_KEY" -ForegroundColor Red
} else {
    Write-Host "[4/5] .env already exists — skipping" -ForegroundColor Green
}

# 5. Run Bronze ingestion
Write-Host "[5/5] Running Bronze ingestion..." -ForegroundColor Yellow
$env:OLIST_CSV_DIR = "data/raw/olist"
$env:DUCKDB_PATH   = "data/ecom.duckdb"
python pipeline/ingest_bronze.py

Write-Host "`n=== Setup complete. Next step: ===" -ForegroundColor Cyan
Write-Host "  cd dbt" -ForegroundColor White
Write-Host "  dbt deps" -ForegroundColor White
Write-Host "  dbt run" -ForegroundColor White
Write-Host "  dbt test`n" -ForegroundColor White
