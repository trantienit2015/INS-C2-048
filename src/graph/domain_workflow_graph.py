"""AgentCore Platform v1.0 — INS-C2-048 inner dual-regulatory workflow (Cat 2).

Instantiated by DualRegGraphNode.get_subgraph(). Receives only the JSON string
user_input (seeded from the outer validated_input); the first inner node
reconstructs the payload.

Pipeline: annex_iii_classify → dual_reg_retrieve → gap_assess → compliance_report
"""

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.annex_iii_classify_node import AnnexIIIClassifyNode
from src.nodes.compliance_report_node import ComplianceReportNode
from src.nodes.dual_reg_retrieve_node import DualRegRetrieveNode
from src.nodes.gap_assess_node import GapAssessNode
from src.schemas.state import State


class DualRegWorkflowGraph(BaseGraph):
    """Inner multi-step dual-regulatory compliance workflow."""

    @property
    def name(self) -> str:
        return "ins_c2_048_dual_reg_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm") if hasattr(self, "config") else None
        retriever = self.config.get("retriever") if hasattr(self, "config") else None
        top_k = self.config.get("top_k", 5) if hasattr(self, "config") else 5
        self._nodes["annex_iii_classify"] = AnnexIIIClassifyNode(llm=llm)
        self._nodes["dual_reg_retrieve"] = DualRegRetrieveNode(retriever=retriever, top_k=top_k)
        self._nodes["gap_assess"] = GapAssessNode(llm=llm)
        self._nodes["compliance_report"] = ComplianceReportNode(llm=llm)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "annex_iii_classify")
        self._sg.add_edge("annex_iii_classify", "dual_reg_retrieve")
        self._sg.add_edge("dual_reg_retrieve", "gap_assess")
        self._sg.add_edge("gap_assess", "compliance_report")
        self._sg.add_edge("compliance_report", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "compliance_report"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "annex_iii_points": state.get("annex_iii_points", []),
            "classification_rationale": state.get("classification_rationale", ""),
            "high_risk": state.get("high_risk", False),
            "retrieved_obligations": state.get("retrieved_obligations", {}),
            "gaps": state.get("gaps", []),
            "compliance_report": state.get("compliance_report", {}),
            "kb_version": state.get("kb_version", ""),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
