"""Data drift detection: PSI and KS tests.

Compares a reference distribution (the Olist historical core, treated as the
training distribution) against a current distribution (the synthetic live tail,
treated as production traffic). Real drift is expected here because the two
sources differ - which makes this a meaningful demonstration of a drift monitor.

Two complementary measures per numeric feature:
  - PSI (Population Stability Index): bins both distributions and sums the
    relative difference. Common thresholds: < 0.1 stable, 0.1-0.25 moderate,
    > 0.25 significant drift.
  - KS (Kolmogorov-Smirnov) two-sample test: max distance between empirical
    CDFs, with a p-value. Small p-value indicates the distributions differ.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PSI_BINS = 10
PSI_STABLE = 0.1
PSI_MODERATE = 0.25


@dataclass
class DriftResult:
    feature: str
    psi: float
    psi_band: str          # "stable" | "moderate" | "significant"
    ks_statistic: float
    ks_pvalue: float
    drifted: bool


def _psi(reference: np.ndarray, current: np.ndarray, bins: int = PSI_BINS) -> float:
    """Population Stability Index using quantile bins from the reference."""
    reference = reference[~np.isnan(reference)]
    current = current[~np.isnan(current)]
    if len(reference) == 0 or len(current) == 0:
        return 0.0
    # Quantile edges from the reference; guard against duplicate edges.
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_pct = np.histogram(reference, bins=edges)[0] / len(reference)
    cur_pct = np.histogram(current, bins=edges)[0] / len(current)
    # Avoid division by zero / log(0) with a small epsilon.
    eps = 1e-6
    ref_pct = np.clip(ref_pct, eps, None)
    cur_pct = np.clip(cur_pct, eps, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _psi_band(psi: float) -> str:
    if psi < PSI_STABLE:
        return "stable"
    if psi < PSI_MODERATE:
        return "moderate"
    return "significant"


def compute_drift(reference: dict[str, np.ndarray],
                  current: dict[str, np.ndarray]) -> list[DriftResult]:
    """Compute PSI and KS for each shared feature.

    Args:
        reference: feature name -> reference values.
        current: feature name -> current values.

    Returns:
        One DriftResult per shared feature.
    """
    from scipy import stats

    results = []
    for feat in reference:
        if feat not in current:
            continue
        ref = np.asarray(reference[feat], dtype=float)
        cur = np.asarray(current[feat], dtype=float)
        ref = ref[~np.isnan(ref)]
        cur = cur[~np.isnan(cur)]
        if len(ref) < 2 or len(cur) < 2:
            continue
        psi = _psi(ref, cur)
        ks = stats.ks_2samp(ref, cur)
        band = _psi_band(psi)
        results.append(
            DriftResult(
                feature=feat,
                psi=round(psi, 4),
                psi_band=band,
                ks_statistic=round(float(ks.statistic), 4),
                ks_pvalue=round(float(ks.pvalue), 6),
                drifted=bool(band != "stable" or ks.pvalue < 0.05),
            )
        )
    return results
