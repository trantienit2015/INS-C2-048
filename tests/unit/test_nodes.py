# INS-C2-048 — Unit tests (per node: success + error/edge).

import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.annex_iii_classify_node import AnnexIIIClassifyNode
from src.nodes.compliance_report_node import DISCLAIMER, ComplianceReportNode
from src.nodes.dual_reg_retrieve_node import DualRegRetrieveNode
from src.nodes.gap_assess_node import GapAssessNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.services import eu_ai_act_service as eas


def _s(**kw):
    st = {"node_history": [], "error_log": [], "execution_time": {}, "correlation_id": "c"}
    st.update(kw)
    return st


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success(self):
        p = json.dumps({"system_description": "underwriting AI", "compliance_question": "high risk?"})
        r = self.node.execute(_s(user_input=p))
        assert r["status"] == AgentStatus.SUCCESS
        assert json.loads(r["validated_input"])["system_description"] == "underwriting AI"

    def test_empty(self):
        assert self.node.execute(_s(user_input=""))["status"] == AgentStatus.ERROR

    def test_rejects_jwt(self):
        p = json.dumps({"system_description": "token eyJabc.def.ghi here", "compliance_question": "q"})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR

    def test_rejects_mynumber(self):
        p = json.dumps({"system_description": "claimant 1234-5678-9012 underwriting", "compliance_question": "q"})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR


class TestAnnexIIIClassifyNode:
    def setup_method(self):
        self.node = AnnexIIIClassifyNode()

    def test_underwriting_high_risk(self):
        inner = json.dumps({"system_description": "underwriting risk scoring AI", "compliance_question": "q"})
        r = self.node.execute(_s(user_input=inner))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["high_risk"] is True
        assert "point_5b_credit_scoring_adjacent" in r["annex_iii_points"]

    def test_unclassified(self):
        inner = json.dumps({"system_description": "a coffee ordering bot", "compliance_question": "q"})
        r = self.node.execute(_s(user_input=inner))
        assert r["high_risk"] is False

    def test_missing_description(self):
        assert self.node.execute(_s(user_input=json.dumps({})))["status"] == AgentStatus.ERROR


class TestDualRegRetrieveNode:
    def setup_method(self):
        self.node = DualRegRetrieveNode()

    def test_all_corpora(self):
        r = self.node.execute(_s(annex_iii_points=["point_5_essential_services"], compliance_question="q"))
        assert r["status"] == AgentStatus.SUCCESS
        assert set(r["retrieved_obligations"].keys()) == set(eas.ALL_CORPORA)
        assert eas.kb_version_present(r["kb_version"])

    def test_upstream_error_propagates(self):
        r = self.node.execute(_s(status=AgentStatus.ERROR.value))
        assert r["status"] == AgentStatus.ERROR


class TestGapAssessNode:
    def setup_method(self):
        self.node = GapAssessNode()

    def test_gaps_high_priority_for_eu_high_risk(self):
        retrieved = {c: [] for c in eas.ALL_CORPORA}
        r = self.node.execute(_s(high_risk=True, retrieved_obligations=retrieved))
        assert r["status"] == AgentStatus.SUCCESS
        eu = [g for g in r["gaps"] if g["regulation"] == eas.EU_AI_ACT]
        assert eu and all(g["priority"] == "high" for g in eu)

    def test_upstream_error(self):
        assert self.node.execute(_s(status="error"))["status"] == AgentStatus.ERROR


class TestComplianceReportNode:
    def setup_method(self):
        self.node = ComplianceReportNode()

    def test_report_schema(self):
        gaps = [{"regulation": eas.EU_AI_ACT, "reference": "Art.11", "obligation": "docs", "status": "review_required", "priority": "high"}]
        r = self.node.execute(_s(annex_iii_points=["point_5_essential_services"], high_risk=True, gaps=gaps, kb_version=eas.KB_VERSION))
        rep = r["compliance_report"]
        assert rep["disclaimer"] == DISCLAIMER
        assert eas.kb_version_present(rep["kb_version"])
        assert rep["annex_iii_verdict"]["high_risk"] is True

    def test_upstream_error(self):
        assert self.node.execute(_s(status="ERROR"))["status"] == AgentStatus.ERROR


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_success(self):
        rep = {"annex_iii_verdict": {"high_risk": True}, "disclaimer": DISCLAIMER, "kb_version": eas.KB_VERSION}
        r = self.node.execute(_s(compliance_report=rep))
        assert r["status"] == AgentStatus.SUCCESS

    def test_upstream_error(self):
        assert self.node.execute(_s(status="error"))["status"] == AgentStatus.ERROR

    def test_s3_gate_missing_disclaimer(self):
        bad = _s(compliance_report={"disclaimer": "x", "kb_version": eas.KB_VERSION})
        assert self.node._extra_security_gate_output(bad)["status"] == AgentStatus.ERROR

    def test_s3_gate_definitive_verdict_blocked(self):
        rep = {"disclaimer": DISCLAIMER, "kb_version": eas.KB_VERSION, "note": "you are compliant"}
        assert self.node._extra_security_gate_output(_s(compliance_report=rep))["status"] == AgentStatus.ERROR

    def test_s3_gate_passes_valid(self):
        good = _s(compliance_report={"disclaimer": DISCLAIMER, "kb_version": eas.KB_VERSION})
        assert self.node._extra_security_gate_output(good) is good
