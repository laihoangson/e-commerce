## RetailLens Dashboards

The frontend is now split into two separate dashboard pages:

- `olist.html` - Olist Historical Intelligence for the real 2016-2018 dataset.
- `synthetic.html` - Synthetic Growth Command Center for the disclosed 2024-2026 live tail.

`index.html` is a small dashboard hub, while the repository root `../index.html`
is the public home page that explains the two-dashboard concept and links to
both pages.

### Data Sources

- Olist dashboard source: `olist`
- Synthetic dashboard source: `faker_live`

### API Dependencies

The frontend expects the FastAPI service configured in `config.js`.

The synthetic period selector uses:

```text
/api/revenue/timeseries?source=faker_live&period=day|week|month|year&start=YYYY-MM-DD&end=YYYY-MM-DD
```

### Local Test

The pages are static, so they can be opened directly in a browser. If browser
CORS behavior blocks remote API calls from `file://`, serve the folder instead:

```powershell
cd dashboard
python -m http.server 8080
```

Then open `http://localhost:8080`.
