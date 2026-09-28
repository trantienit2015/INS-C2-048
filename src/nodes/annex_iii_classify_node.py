"""AgentCore Platform v1.0 — inner step 1: Annex III classification."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eu_ai_act_service as eas


class AnnexIIIClassifyNode(FunctionNode):
    """Classify the described insurance AI system against EU AI Act Annex III.

    The inner subgraph receives only the JSON string user_input (seeded from the
    outer validated_input), so this first inner node reconstructs the payload.
    LLM NL reasoning refines the deterministic taxonomy classification when an
    LLM is configured; the deterministic result is the guaranteed fallback.
    """

    # S-1 (the independent review R1 #2): inner subgraph node (invoked via DualRegGraphNode) —
    # ANONYMOUS. Caller trust is authenticated once at the outer backbone
    # (pre_process); inner nodes must not re-demand INTERNAL or external
    # callers cannot satisfy the escalated requirement.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict) or not payload.get("system_description"):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["AnnexIIIClassifyNode: missing system_description in inner input"],
            }

        description = payload["system_description"]
        points, rationale = eas.classify_annex_iii(description)
        rationale = self._llm_rationale(description, points, rationale)
        emit_trace_event(
            "annex_iii_classified",
            {"correlation_id": state.get("correlation_id"), "points": points},
            state,
        )
        return {
            "system_description": description,
            "compliance_question": str(payload.get("compliance_question", "") or ""),
            "annex_iii_points": points,
            "classification_rationale": rationale,
            "high_risk": eas.is_high_risk(points),
            "status": AgentStatus.SUCCESS.value,
        }

    def _llm_rationale(self, description: str, points: list[str], base: str) -> str:
        if self._llm is None:
            return base
        try:
            response = self._llm.complete(
                [
                    {
                        "role": "user",
                        "content": (
                            f"Explain the EU AI Act Annex III classification {points} for "
                            f"this insurance AI system: {description[:500]}"
                        ),
                    }
                ]
            )
            content = response.get("content") if isinstance(response, dict) else response
            return str(content).strip() or base
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic rationale
            import logging

            logging.getLogger(__name__).warning("annex III LLM rationale failed: %s", exc)
            return base
