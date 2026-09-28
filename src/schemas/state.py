"""AgentCore Platform v1.0 — INS-C2-048 state schema."""

# Flat TypedDict only (msgpack-safe). Extend AgentState with agent-specific
# fields; no credentials, secrets, or Pydantic models in State.

from typing import Any, NotRequired

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Insurance AI System EU AI Act Compliance Q&A Agent state.

    Shared fields (user_input, validated_input, status, node_history, result,
    formatted_output, ...) are inherited from AgentState. All agent-specific
    fields are NotRequired[...] (state-safety) and read via state.get(...).
    """

    system_description: NotRequired[str]
    compliance_question: NotRequired[str]
    # EU AI Act Annex III classification result.
    annex_iii_points: NotRequired[list[str]]
    classification_rationale: NotRequired[str]
    high_risk: NotRequired[bool]
    # Retrieved obligation passages keyed by corpus.
    retrieved_obligations: NotRequired[dict[str, Any]]
    # Structured cross-regulatory gap list.
    gaps: NotRequired[list[dict[str, Any]]]
    # Final assembled compliance report.
    compliance_report: NotRequired[dict[str, Any]]
    kb_version: NotRequired[str]
