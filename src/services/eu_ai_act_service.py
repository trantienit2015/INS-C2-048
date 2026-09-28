"""AgentCore Platform v1.0 — EU AI Act / dual-regulatory helpers (deterministic).

Service layer: pure deterministic domain helpers (the "Tool" layer the Agent
wraps). No routing, no credentials, no side effects. LLM reasoning and
orchestration stay in the nodes.
"""

from __future__ import annotations

import re

# Corpora indexed in the KB.
EU_AI_ACT = "eu_ai_act"
HOKEN_GYOHO = "hoken_gyoho"  # 保険業法
FSA_MRM = "fsa_mrm"  # FSA model-risk-management circular

ALL_CORPORA = (EU_AI_ACT, HOKEN_GYOHO, FSA_MRM)

# Knowledge-base version stamp (snapshot corpus).
KB_VERSION = "2026-07-eu-ai-act.hoken-gyoho.fsa-mrm.v1"

# Insurance-domain Annex III taxonomy: keyword -> Annex III point(s).
_TAXONOMY: tuple[tuple[str, str], ...] = (
    ("underwrit", "point_5b_credit_scoring_adjacent"),
    ("credit scor", "point_5b_credit_scoring_adjacent"),
    ("solicit", "point_5_essential_services"),
    ("recommend", "point_5_essential_services"),
    ("biometric", "point_1_biometric"),
    ("kyc", "point_1_biometric"),
    ("claims", "point_5_essential_services"),
    ("fraud", "point_5_essential_services"),
    ("agent employ", "point_4_employment"),
    ("recruit", "point_4_employment"),
)

# Phrases that would constitute a definitive legal verdict — must NOT appear.
_DEFINITIVE_VERDICT_PHRASES = (
    "you are compliant",
    "this is legal",
    "fully compliant",
    "guaranteed compliant",
    "no legal risk",
)


def classify_annex_iii(description: str) -> tuple[list[str], str]:
    """Deterministic keyword-based Annex III classification fallback.

    Returns (annex_points, rationale). An LLM refines this in the node; this
    guarantees a defined result even when no LLM is configured.
    """
    text = (description or "").lower()
    hits: list[str] = []
    reasons: list[str] = []
    for keyword, point in _TAXONOMY:
        if keyword in text and point not in hits:
            hits.append(point)
            reasons.append(f"matched '{keyword}' -> {point}")
    if not hits:
        return ["unclassified"], "no insurance Annex III taxonomy keyword matched"
    return hits, "; ".join(reasons)


def is_high_risk(annex_points: list[str]) -> bool:
    """Any concrete Annex III point (not 'unclassified') marks high-risk."""
    return any(p != "unclassified" for p in annex_points)


def corpora_for(annex_points: list[str]) -> list[str]:
    """All three corpora always apply for insurance dual-regulatory review."""
    # Insurance AI review is inherently cross-regulatory; retrieve all corpora,
    # order-stable for deterministic output.
    return list(ALL_CORPORA)


def has_definitive_verdict(text: str) -> bool:
    """Whether the report text contains a prohibited definitive-verdict phrase."""
    low = (text or "").lower()
    return any(phrase in low for phrase in _DEFINITIVE_VERDICT_PHRASES)


_KB_VERSION_RE = re.compile(r"\bv\d+\b")


def kb_version_present(stamp: str | None) -> bool:
    """Whether a KB version stamp is present and well-formed."""
    return bool(stamp) and bool(_KB_VERSION_RE.search(str(stamp)))


def is_upstream_error(status: object) -> bool:
    """Whether a prior inner node already set a terminal ERROR status."""
    return status in ("error", "ERROR") or (status is not None and getattr(status, "value", None) == "error")
