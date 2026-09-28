# INS-C2-048 - Framework compliance tests TC-01..TC-08.
# Reference shape: another template tests/unit/test_framework_compliance.py,
# adapted to this template's real architecture (Cat 2: outer pre/post + GraphNode-wrapped inner nodes).

import json
import os
import re
import typing
from typing import NotRequired

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import annex_iii_classify_node, post_process_node, pre_process_node
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.ANONYMOUS.value


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _unwrap(ann):
    """Strip NotRequired[...] so the underlying primitive type can be checked."""
    if typing.get_origin(ann) is NotRequired:
        args = typing.get_args(ann)
        return args[0] if args else ann
    return ann


# TC-01 - State is a flat TypedDict extending AgentState, added fields are JSON-safe primitives.
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_json_safe(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        allowed = {"str", "int", "bool", "float", "list", "dict"}
        for name in added:
            ann = _unwrap(State.__annotations__[name])
            origin = typing.get_origin(ann)
            ann_str = getattr(origin or ann, "__name__", str(ann))
            assert ann_str in allowed, f"{name}: {ann_str} - must be msgpack-safe (no Pydantic/dataclass)"


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = pre_process_node.PreProcessNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_missing_system_description_no_raise(self):
        node = annex_iii_classify_node.AnnexIIIClassifyNode()
        out = node.execute({"user_input": json.dumps({"compliance_question": "no description"})})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # The standalone entry point is the ONE permitted os.environ reader: it
        # authenticates the caller (INVOKE_AUTH_TOKEN) BEFORE any InvocationContext
        # exists, so ctx.secrets cannot apply. That token is a deployment-level
        # caller credential, not an agent secret, and is never stored in state.
        # See the framework rules / the STG runbook.
        offenders = []
        for fp in _src_files():
            if os.path.normpath(fp).endswith(os.path.join("src", "api", "server.py")):
                continue
            with open(fp, encoding="utf-8") as f:
                if "os.environ" in f.read():
                    offenders.append(fp)
        assert offenders == []

    def test_entry_point_env_read_is_limited_to_the_caller_auth_token(self):
        """The entry-point exception is narrow: only the two caller credentials may be read."""
        import re

        server = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "src", "api", "server.py")
        if not os.path.exists(server):
            return
        with open(server, encoding="utf-8") as f:
            content = f.read()
        reads = re.findall(r"os\.environ(?:\.get)?[(\[]\s*[\"']([A-Z_]+)[\"']", content)
        # Two deployment-level caller credentials are sanctioned at this boundary: the
        # external bearer token and the separate staging-only runner token that maps to
        # INTERNAL. Anything else read from the environment here is still a violation.
        assert set(reads) <= {"INVOKE_AUTH_TOKEN", "STG_INTERNAL_RUNNER_TOKEN"}, (
            f"unexpected env reads: {reads}"
        )


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph()
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.INTERNAL, caller_id="agent-tc04")
        payload = json.dumps({"system_description": "An AI system used for insurance underwriting decisions."})
        result = agent.invoke(payload, ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: every node emits >=1 domain event on its success path;
# no node under src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_pre_process_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(pre_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = pre_process_node.PreProcessNode().execute(
            {"user_input": json.dumps({"system_description": "An insurance claims triage AI system."})}
        )
        assert out["status"] == AgentStatus.SUCCESS
        assert len(events) >= 1
        assert "input_validate_started" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_post_process_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(post_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = post_process_node.PostProcessNode().execute(
            {"compliance_report": {"disclaimer": "x", "kb_version": "2026-07"}}
        )
        assert out["status"] == AgentStatus.SUCCESS
        assert len(events) >= 1
        assert "output_validated" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert post_process_node.PostProcessNode._extra_security_gate_output is not FunctionNode._extra_security_gate_output

    def test_output_gate_blocks_missing_disclaimer(self):
        # The @final S-3 preservation gate actually fires (not vacuous): output
        # missing the mandatory counsel disclaimer is blocked, never returned as-is.
        node = post_process_node.PostProcessNode()
        out = node._extra_security_gate_output({"compliance_report": {"kb_version": "2026-07"}})
        assert out["status"] == AgentStatus.ERROR


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        from src.graph.graph import DualRegGraphNode

        for cls in (
            pre_process_node.PreProcessNode,
            post_process_node.PostProcessNode,
            DualRegGraphNode,
            annex_iii_classify_node.AnnexIIIClassifyNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        from src.graph.graph import DualRegGraphNode

        node = DualRegGraphNode(llm=None, retriever=None)
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "validated_input": "{}"})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = pre_process_node.PreProcessNode()
        out = node(
            {
                "caller_trust_level": TRUST,
                "user_input": json.dumps({"system_description": "An insurance underwriting AI system."}),
            }
        )
        assert out["status"] == AgentStatus.SUCCESS
