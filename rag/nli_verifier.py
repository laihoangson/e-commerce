"""NLI-based claim verifier for chart interpretations.

Each interpretation is a set of natural-language claims about a chart. The LLM
that writes them can hallucinate numbers, so every claim is checked against the
chart's own numeric evidence using a Natural Language Inference (NLI) model: the
claim is the hypothesis, the evidence is the premise. A claim is "verified" only
if the model predicts entailment with enough confidence.

The NLI model is injected (a callable taking a list of (premise, hypothesis)
pairs and returning per-pair label scores), so this module stays testable and
free of a hard dependency on any specific model at import time. Production wires
in a sentence-transformers CrossEncoder; tests pass a stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

# A scorer maps (premise, hypothesis) pairs to a dict of label -> probability,
# with labels among {"entailment", "neutral", "contradiction"}.
NLIScorer = Callable[[Sequence[tuple[str, str]]], list[dict[str, float]]]

ENTAILMENT_THRESHOLD = 0.5


@dataclass
class ClaimVerdict:
    claim: str
    evidence: str
    label: str
    entailment_score: float
    verified: bool


def verify_claims(
    claims: Sequence[tuple[str, str]],
    scorer: NLIScorer,
    threshold: float = ENTAILMENT_THRESHOLD,
) -> list[ClaimVerdict]:
    """Verify each (claim, evidence) pair with the NLI scorer.

    Args:
        claims: list of (claim_text, evidence_text). The claim is the hypothesis,
            the evidence (the chart's numbers stated plainly) is the premise.
        scorer: NLI scorer callable.
        threshold: minimum entailment probability to mark a claim verified.

    Returns:
        One ClaimVerdict per input pair.
    """
    if not claims:
        return []
    # premise = evidence, hypothesis = claim
    pairs = [(evidence, claim) for (claim, evidence) in claims]
    scores = scorer(pairs)
    verdicts = []
    for (claim, evidence), s in zip(claims, scores):
        ent = float(s.get("entailment", 0.0))
        label = max(s, key=s.get) if s else "neutral"
        verdicts.append(
            ClaimVerdict(
                claim=claim,
                evidence=evidence,
                label=label,
                entailment_score=round(ent, 4),
                verified=bool(ent >= threshold and label == "entailment"),
            )
        )
    return verdicts


def summarize(verdicts: Sequence[ClaimVerdict]) -> dict:
    """Aggregate verdicts into a small summary for storage and display."""
    total = len(verdicts)
    verified = sum(v.verified for v in verdicts)
    return {
        "total_claims": total,
        "verified_claims": verified,
        "verified_rate": round(verified / total, 3) if total else 0.0,
        "all_verified": total > 0 and verified == total,
    }


def build_crossencoder_scorer(model_name: str = "cross-encoder/nli-deberta-v3-xsmall") -> NLIScorer:
    """Build a production NLI scorer backed by a sentence-transformers CrossEncoder.

    Imported lazily so the heavy ML dependency is only needed when actually
    running verification (offline), never at module import time.

    We force the PyTorch backend and disable TensorFlow/Flax. Recent
    `transformers` versions otherwise try to import TensorFlow during model
    loading, which crashes with a DLL error on many Windows setups. We do not
    need TF at all here.
    """
    import os

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name)
    # CrossEncoder NLI label order for this family: contradiction, entailment, neutral
    id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}

    def scorer(pairs: Sequence[tuple[str, str]]) -> list[dict[str, float]]:
        import numpy as np

        raw = model.predict(list(pairs), apply_softmax=True)
        out = []
        for row in np.atleast_2d(raw):
            out.append({id2label[i]: float(row[i]) for i in range(len(row))})
        return out

    return scorer
