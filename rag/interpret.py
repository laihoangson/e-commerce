"""Generate natural-language interpretations of dashboard charts via Groq.

Each chart's data is turned into (a) a compact evidence string stating the key
numbers, and (b) an LLM-written interpretation broken into short claims. Each
claim is paired with the evidence and later checked by the NLI verifier.

The LLM client is injected so this module is testable without network access.
Production wires in a Groq client; tests pass a stub returning canned JSON.
"""

from __future__ import annotations

import json
from typing import Callable

# An LLM client maps a prompt string to a completion string.
LLMClient = Callable[[str], str]

SYSTEM_RULES = (
    "You are a precise data analyst. Given a chart's data, write 2-3 short, "
    "factual claims interpreting it. Every claim must be directly supported by "
    "the numbers provided - never invent figures. Respond ONLY with a JSON list "
    "of strings, no preamble, no markdown."
)


def build_prompt(chart_title: str, evidence: str) -> str:
    return (
        f"{SYSTEM_RULES}\n\n"
        f"Chart: {chart_title}\n"
        f"Data (the only facts you may use):\n{evidence}\n\n"
        f'Respond with JSON like ["claim one.", "claim two."]'
    )


def parse_claims(raw: str) -> list[str]:
    """Parse the LLM response into a list of claim strings, robustly."""
    text = raw.strip()
    # strip code fences if present
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip("` \n")
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(c).strip() for c in data if str(c).strip()]
    except json.JSONDecodeError:
        pass
    # fallback: split on newlines/sentences
    return [line.strip("-* \t") for line in text.splitlines() if line.strip()][:3]


def interpret_chart(chart_title: str, evidence: str, llm: LLMClient) -> list[str]:
    """Generate interpretation claims for one chart."""
    prompt = build_prompt(chart_title, evidence)
    raw = llm(prompt)
    return parse_claims(raw)


def build_groq_client(model: str = "llama-3.3-70b-versatile") -> LLMClient:
    """Build a production LLM client backed by Groq.

    Imported lazily so the dependency and API key are only needed at run time.
    """
    import os

    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        return resp.choices[0].message.content or ""

    return call
