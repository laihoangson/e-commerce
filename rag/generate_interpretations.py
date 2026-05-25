"""Offline job: generate and verify chart interpretations, then store them.

Pipeline per chart:
  1. Build an evidence string from Gold data.
  2. Ask Groq to write 2-3 factual claims about it.
  3. Verify each claim against the evidence with the NLI model.
  4. Keep verified claims; flag the rest.

The result is uploaded to Supabase Storage as chart_interpretations.json, which
the API serves and the dashboard displays under each chart with a "verified"
badge. This runs offline (local or CI) because the NLI model is heavy; the API
never loads it.

Usage:
    python rag/generate_interpretations.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Force PyTorch-only backend for transformers BEFORE any heavy import, so it
# never tries to load TensorFlow (which crashes with a DLL error on Windows).
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from chart_evidence import CHART_BUILDERS, ab_evidence  # noqa: E402
from interpret import build_groq_client, interpret_chart  # noqa: E402
from nli_verifier import build_crossencoder_scorer, summarize, verify_claims  # noqa: E402
from utils.artifact_store import upload_artifact  # noqa: E402
from utils.duckdb_client import get_connection  # noqa: E402

SCHEMA = "main_gold"
ARTIFACT_NAME = "chart_interpretations.json"


def process_chart(key, title, evidence, llm, scorer) -> dict:
    claims = interpret_chart(title, evidence, llm)
    verdicts = verify_claims([(c, evidence) for c in claims], scorer)
    return {
        "chart": key,
        "title": title,
        "evidence": evidence,
        "claims": [
            {"text": v.claim, "verified": v.verified,
             "label": v.label, "entailment": v.entailment_score}
            for v in verdicts
        ],
        "summary": summarize(verdicts),
    }


def main() -> int:
    con = get_connection()
    llm = build_groq_client()
    scorer = build_crossencoder_scorer()

    output = {"generated_at": datetime.utcnow().isoformat(), "charts": {}}

    # Source-scoped charts: generate for both the real and live tabs.
    for source, tab in [("olist", "real"), ("faker_live", "live")]:
        for key, (title, builder) in CHART_BUILDERS.items():
            evidence = builder(con, SCHEMA, source)
            if evidence.startswith("No "):
                continue
            result = process_chart(f"{key}", title, evidence, llm, scorer)
            output["charts"][f"{tab}:{key}"] = result
            v = result["summary"]
            print(f"[{tab}:{key}] {v['verified_claims']}/{v['total_claims']} verified")

    # A/B is live-only.
    ab_ev = ab_evidence(con, SCHEMA)
    if not ab_ev.startswith("No "):
        result = process_chart("ab", "A/B Experiments", ab_ev, llm, scorer)
        output["charts"]["live:ab"] = result
        v = result["summary"]
        print(f"[live:ab] {v['verified_claims']}/{v['total_claims']} verified")

    con.close()

    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(tmp, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    remote = upload_artifact(tmp, ARTIFACT_NAME)
    os.remove(tmp)
    print(f"Uploaded {len(output['charts'])} interpretations to {remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
