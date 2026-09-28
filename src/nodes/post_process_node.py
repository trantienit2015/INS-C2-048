"""AgentCore Platform v1.0 — outer post_process: OutputValidate (S-3 gate)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.compliance_report_node import DISCLAIMER
from src.services import eu_ai_act_service as eas


class PostProcessNode(FunctionNode):
    """Finalize + S-3 deterministic output gate.

    Asserts the mandatory counsel disclaimer AND a KB version stamp are present,
    and that no definitive-verdict phrasing appears. The preservation+filter
    variant of the S-3 hook rejects output that drops the disclaimer/stamp or
    leaks a definitive verdict.
    """

    # S-1: read merged report and format — no privileged operation.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        status = state.get("status")
        if status in ("error", "ERROR") or getattr(status, "value", None) == "error":
            emit_trace_event(
                "output_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        report = state.get("compliance_report") or {}
        emit_trace_event(
            "output_validated",
            {
                "correlation_id": state.get("correlation_id"),
                "high_risk": report.get("annex_iii_verdict", {}).get("high_risk"),
            },
            state,
        )
        return {
            "compliance_report": report,
            "formatted_output": report,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation + filter variant (framework-invoked; never raises)."""
        report = state.get("compliance_report") or {}
        if not report:
            return state
        if report.get("disclaimer") != DISCLAIMER:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputValidateNode: mandatory counsel disclaimer missing"],
            }
        if not eas.kb_version_present(report.get("kb_version")):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputValidateNode: KB version stamp missing/invalid"],
            }
        if eas.has_definitive_verdict(json.dumps(report, ensure_ascii=False)):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputValidateNode: definitive-verdict phrasing blocked"],
            }
        return state
