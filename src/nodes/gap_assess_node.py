"""AgentCore Platform v1.0 — inner step 3: gap assessment."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eu_ai_act_service as eas

# Baseline obligation checklist per corpus (deterministic gap seeds; an LLM
# refines these against the described system when configured).
_OBLIGATIONS = {
    eas.EU_AI_ACT: [
        ("Art.11", "Technical documentation for high-risk AI system"),
        ("Art.14", "Human oversight measures"),
        ("Art.9", "Risk management system"),
    ],
    eas.HOKEN_GYOHO: [
        ("Art.300", "Solicitation conduct obligations (保険業法)"),
    ],
    eas.FSA_MRM: [
        ("MRM", "Model validation and monitoring evidence"),
    ],
}


class GapAssessNode(FunctionNode):
    """Enumerate compliance gaps: retrieved obligations vs the described system."""

    # S-1 (the independent review R1 #2): inner subgraph node (invoked via DualRegGraphNode) —
    # ANONYMOUS. Caller trust is authenticated once at the outer backbone;
    # inner nodes must not re-demand INTERNAL.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if eas.is_upstream_error(state.get("status")):
            return {"status": AgentStatus.ERROR.value}
        high_risk = state.get("high_risk", False)
        retrieved = state.get("retrieved_obligations", {}) or {}

        gaps: list[dict[str, Any]] = []
        for corpus, obligations in _OBLIGATIONS.items():
            # Only assess corpora that were in scope (present in retrieval mapping).
            if corpus not in retrieved:
                continue
            for ref, obligation in obligations:
                gaps.append(
                    {
                        "regulation": corpus,
                        "reference": ref,
                        "obligation": obligation,
                        "status": "review_required",
                        "priority": "high" if (high_risk and corpus == eas.EU_AI_ACT) else "medium",
                    }
                )

        emit_trace_event(
            "gaps_assessed",
            {"correlation_id": state.get("correlation_id"), "n_gaps": len(gaps)},
            state,
        )
        return {"gaps": gaps, "status": AgentStatus.SUCCESS.value}
