"""AgentCore Platform v1.0 — inner step 4: cross-regulatory report synthesis."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eu_ai_act_service as eas

DISCLAIMER = (
    "This is AI-assisted regulatory analysis, not legal advice. It emits no "
    "definitive legal verdict. Consult qualified EU/Japan regulatory counsel "
    "before acting."
)


class ComplianceReportNode(FunctionNode):
    """Synthesize the cross-regulatory compliance report (locked output schema)."""

    # S-1 (the independent review R1 #2): inner subgraph node (invoked via DualRegGraphNode) —
    # ANONYMOUS. Caller trust is authenticated once at the outer backbone;
    # inner nodes must not re-demand INTERNAL.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if eas.is_upstream_error(state.get("status")):
            return {"status": AgentStatus.ERROR.value}
        annex_points = state.get("annex_iii_points", [])
        high_risk = state.get("high_risk", False)
        gaps = state.get("gaps", [])
        kb_version = state.get("kb_version", eas.KB_VERSION)

        art11_checklist = [
            g["obligation"] for g in gaps if g.get("regulation") == eas.EU_AI_ACT and g.get("reference") == "Art.11"
        ] or ["Technical documentation per EU AI Act Art.11 (Annex IV)"]
        hokengyoho_obligations = [g["obligation"] for g in gaps if g.get("regulation") == eas.HOKEN_GYOHO]

        report = {
            "annex_iii_verdict": {"points": annex_points, "high_risk": high_risk},
            "gaps": gaps,
            "art11_checklist": art11_checklist,
            "hokengyoho_obligations": hokengyoho_obligations,
            "disclaimer": DISCLAIMER,
            "kb_version": kb_version,
        }
        emit_trace_event(
            "compliance_report_synthesized",
            {"correlation_id": state.get("correlation_id"), "n_gaps": len(gaps)},
            state,
        )
        return {"compliance_report": report, "status": AgentStatus.SUCCESS.value}
