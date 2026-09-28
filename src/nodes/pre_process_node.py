"""AgentCore Platform v1.0 — outer pre_process: InputValidate (S-1 + S-2)."""

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

MAX_INPUT_CHARS = 100_000

# S-2 deterministic sensitive-content patterns (non-LLM).
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
# マイナンバー / 個人番号: 12-digit personal number (optionally hyphenated 4-4-4).
_MYNUMBER_RE = re.compile(r"\b\d{4}-?\d{4}-?\d{4}\b")


class PreProcessNode(FunctionNode):
    """Validate the request, scan for sensitive content, serialize inner input.

    Accepts a JSON payload:
        {"system_description": "<text>", "compliance_question": "<text>"}
    Rejects payloads containing JWT/Bearer tokens or マイナンバー/個人番号-shaped PII
    (deterministic, not an LLM check). Serializes to validated_input (JSON string)
    for the inner subgraph.
    """

    # S-1: read-only validation; the compliance evaluation itself runs INTERNAL downstream.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        raw = state.get("user_input", "")
        emit_trace_event(
            "input_validate_started",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        if not isinstance(raw, str) or not raw.strip():
            return {"status": AgentStatus.ERROR.value, "error_log": ["PreProcessNode: empty input"]}
        if len(raw) > MAX_INPUT_CHARS:
            return {"status": AgentStatus.ERROR.value, "error_log": ["PreProcessNode: input too large"]}

        # S-2 deterministic scan before any downstream processing / logging.
        if _JWT_RE.search(raw) or _BEARER_RE.search(raw) or _MYNUMBER_RE.search(raw):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: sensitive content (token / マイナンバー-shaped PII) rejected"],
            }

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = {"system_description": raw, "compliance_question": ""}
        if not isinstance(payload, dict):
            return {"status": AgentStatus.ERROR.value, "error_log": ["PreProcessNode: payload must be a JSON object"]}

        description = str(payload.get("system_description", "") or "")
        question = str(payload.get("compliance_question", "") or "")
        if not description.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: 'system_description' is empty"],
            }

        normalized = {"system_description": description, "compliance_question": question}
        return {
            "system_description": description,
            "compliance_question": question,
            "validated_input": json.dumps(normalized, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }
