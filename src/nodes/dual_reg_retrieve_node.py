"""AgentCore Platform v1.0 — inner step 2: dual-regulatory retrieval."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eu_ai_act_service as eas


class DualRegRetrieveNode(FunctionNode):
    """Retrieve obligations across the EU AI Act + 保険業法 + FSA MRM corpora.

    Dense + metadata-key-filtered retrieval (filter by `corpus` and `annex_point`
    from the classification step) via the injected `retriever`. When no retriever
    is configured, returns an empty-per-corpus mapping so the downstream gap
    assessment still runs deterministically.
    """

    # S-1 (the independent review R1 #2): inner subgraph node (invoked via DualRegGraphNode) —
    # ANONYMOUS. Caller trust is authenticated once at the outer backbone;
    # inner nodes must not re-demand INTERNAL.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, retriever: Any | None = None, top_k: int = 5):
        self._retriever = retriever
        self._top_k = top_k

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if eas.is_upstream_error(state.get("status")):
            return {"status": AgentStatus.ERROR.value}
        annex_points = state.get("annex_iii_points", [])
        question = state.get("compliance_question", "")
        corpora = eas.corpora_for(annex_points)

        retrieved: dict[str, list[Any]] = {}
        for corpus in corpora:
            retrieved[corpus] = self._retrieve(corpus, annex_points, question)

        emit_trace_event(
            "dual_reg_retrieved",
            {
                "correlation_id": state.get("correlation_id"),
                "corpora": corpora,
                "counts": {c: len(v) for c, v in retrieved.items()},
            },
            state,
        )
        return {
            "retrieved_obligations": retrieved,
            "kb_version": eas.KB_VERSION,
            "status": AgentStatus.SUCCESS.value,
        }

    def _retrieve(self, corpus: str, annex_points: list[str], question: str) -> list[Any]:
        if self._retriever is None:
            return []
        try:
            return list(
                self._retriever.search(
                    query=question,
                    filters={"corpus": corpus, "annex_point": annex_points},
                    top_k=self._top_k,
                )
            )
        except Exception as exc:  # noqa: BLE001 — degrade, keep the corpus empty
            import logging

            logging.getLogger(__name__).warning("retrieval failed for %s: %s", corpus, exc)
            return []
