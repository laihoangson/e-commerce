## RetailLens Dashboard

Static dashboard (vanilla JS) for GitHub Pages. Four sections: Overview KPIs,
Monthly Revenue, A/B Experiments, Order Funnel.

Hybrid data sourcing:
- Computed endpoints (KPIs, A/B lift, monthly revenue) -> FastAPI on Render
- Simple table reads (funnel) -> Supabase REST directly

### 1. Configure

Edit `config.js` and fill in three values:

```javascript
const CONFIG = {
  API_BASE: "https://retaillens-api.onrender.com",   // your Render URL
  SUPABASE_URL: "https://xxxxxxxx.supabase.co",       // your Supabase URL
  SUPABASE_ANON_KEY: "eyJ...",                         // anon/public key only
};
```

The anon key is safe to expose — it only allows what your Row-Level Security
policies permit. Never put the service key here.

### 2. Enable read access on Gold tables (Supabase RLS)

By default Supabase blocks REST reads. The funnel section needs read access to
`funnel_conversion`. In the Supabase SQL editor, run (for each table the
dashboard reads via REST):

```sql
alter table public.funnel_conversion enable row level security;

create policy "public read funnel"
  on public.funnel_conversion
  for select
  to anon
  using (true);
```

This grants anonymous SELECT only (no writes). Repeat for any other table you
later read directly via REST. Tables served only through FastAPI do not need a
policy, because the API connects with the service credentials.

### 3. Test locally

Because the dashboard fetches from remote endpoints, you can open it with any
static server:

```powershell
cd dashboard
python -m http.server 8080
```

Then open http://localhost:8080. On first load the Render API may take ~30–50s
to wake (free tier cold start); reload if a section times out.

### 4. Deploy to GitHub Pages

Commit the `dashboard/` folder, then in the repo: Settings > Pages > Source =
Deploy from a branch > branch `main`, folder `/dashboard` (or move these files
to a `docs/` folder if you prefer the `/docs` option). The site publishes at
`https://<username>.github.io/<repo>/`.

Set the API's `CORS_ORIGINS` env on Render to your Pages origin
(e.g. `https://laihoangson.github.io`) so the browser allows the API calls.
