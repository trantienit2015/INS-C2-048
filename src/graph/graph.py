"""AgentCore Platform v1.0 — INS-C2-048 outer graph (Cat 2).

Outer (AgentBaseGraph): initialize → pre_process(InputValidate) → main(DualRegGraphNode)
→ post_process(OutputValidate) → finalize.
Inner (BaseGraph): annex_iii_classify → dual_reg_retrieve → gap_assess → compliance_report.

The GraphNode wrapper lives in THIS file (not src/nodes/), matching the scaffold
Cat 2 canonical layout — PB-6 (test_pb_invoke_order.py) only discovers BaseNode
subclasses under src/nodes/, so a single-node probe there would incorrectly pull
in the whole inner subgraph's lifecycle. This placement does not exempt the
GraphNode from boundary test coverage: see
tests/proof_of_boundary/test_pb_graphnode_boundary.py for the S-1 trust gate,
boundary-mapping, and gating-delegation proofs.
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class DualRegGraphNode(GraphNode):
    """Wraps the inner dual-regulatory compliance workflow (main slot)."""

    # S-1: outer main-slot node — performs the privileged operation (LLM +
    # retriever + secrets) declared in config/agent.yaml (required_trust_level:
    # INTERNAL). A lifecycle-skip docstring does not substitute for this
    # independent S-1 declaration.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any | None = None, retriever: Any | None = None, top_k: int = 5):
        super().__init__()
        self._llm = llm
        self._retriever = retriever
        self._top_k = top_k

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import DualRegWorkflowGraph

        sg = DualRegWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "dual_reg_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        value = state.get("validated_input", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "dual_reg_workflow_completed",
            {"correlation_id": state.get("correlation_id"), "n_gaps": len(sub_result.get("gaps", []))},
            state,
        )
        return {
            "annex_iii_points": sub_result.get("annex_iii_points", []),
            "classification_rationale": sub_result.get("classification_rationale", ""),
            "high_risk": sub_result.get("high_risk", False),
            "retrieved_obligations": sub_result.get("retrieved_obligations", {}),
            "gaps": sub_result.get("gaps", []),
            "compliance_report": sub_result.get("compliance_report", {}),
            "kb_version": sub_result.get("kb_version", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm, "retriever": self._retriever, "top_k": self._top_k}


class Graph(AgentBaseGraph):
    """INS-C2-048 — Insurance AI System EU AI Act Compliance Q&A Agent."""

    @property
    def name(self) -> str:
        return "ins-c2-048"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        llm = self.config.get("llm") if hasattr(self, "config") else None
        retriever = self.config.get("retriever") if hasattr(self, "config") else None
        top_k = self.config.get("top_k", 5) if hasattr(self, "config") else 5
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = DualRegGraphNode(llm=llm, retriever=retriever, top_k=top_k)
        self._nodes["post_process"] = PostProcessNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
