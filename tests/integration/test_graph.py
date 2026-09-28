# INS-C2-048 — Integration test: full graph compile + invoke.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


class FakeLLM:
    def complete(self, *a, **k):
        return "classification rationale"


def _ctx(session="it-1"):
    return InvocationContext(session_id=session, caller_trust_level=TrustLevel.INTERNAL, caller_id="tester")


def _agent():
    a = Graph(config={"llm": FakeLLM(), "max_retry": 1})
    a.compile()
    return a


def test_full_pipeline_success():
    payload = json.dumps(
        {"system_description": "underwriting risk-scoring AI for auto insurance", "compliance_question": "Is this high-risk?"}
    )
    result = _agent().invoke(payload, ctx=_ctx())
    assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
    nh = result.get("node_history") or []
    assert len(nh) >= 5, f"expected >=5 nodes, got {len(nh)}: {nh}"
    report = result.get("output") or {}
    assert isinstance(report, dict)
    assert report.get("disclaimer")
    assert report.get("kb_version")
    assert report["annex_iii_verdict"]["high_risk"] is True


def test_empty_input_errors():
    result = _agent().invoke("", ctx=_ctx("it-2"))
    assert result["status"] in (
        AgentStatus.ERROR, AgentStatus.ERROR.value, AgentStatus.CANCELLED, AgentStatus.CANCELLED.value,
    )


def test_no_definitive_verdict_or_secret_in_output():
    payload = json.dumps({"system_description": "claims fraud detection AI", "compliance_question": "obligations?"})
    result = _agent().invoke(payload, ctx=_ctx("it-3"))
    blob = json.dumps(result, default=str).lower()
    assert "you are compliant" not in blob and "this is legal" not in blob
    assert "sk-" not in blob and "eyj" not in blob
