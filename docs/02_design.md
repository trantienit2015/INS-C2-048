# Template Design Specification — INS-C2-048

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (in `src/graph/graph.py`) — the graph IS the agent
- **L1 Base**: `AgentBaseGraph` (Cat 2 — outer backbone + `GraphNode` in the `main` slot)
- **Three-Layer Separation**: State (`class State(AgentState)`, all agent-specific fields
  `NotRequired[...]`) / Node (`FunctionNode.execute(self, state) -> dict`) / Graph (outer
  `register_nodes()` + inner `BaseGraph` subgraph).

## Architecture Overview (Cat 2)

```
OUTER (AgentBaseGraph — src/graph/graph.py):
  initialize → pre_process(InputValidate) → main(DualRegGraphNode) → post_process(OutputValidate) → finalize
                                               │  GraphNode.get_subgraph().invoke(validated_input, ctx)
                                               ▼
INNER (BaseGraph — src/graph/domain_workflow_graph.py):
  START → annex_iii_classify → dual_reg_retrieve → gap_assess → compliance_report → END
```

### Node Configuration

| Node | Layer | Responsibility | Trust |
|------|-------|---------------|-------|
| pre_process = `PreProcessNode` (InputValidate) | outer | S-1 trust + S-2 deterministic scan (JWT/Bearer, マイナンバー/個人番号 PII); serialize `validated_input` | ANONYMOUS |
| main = `DualRegGraphNode` | outer | GraphNode wrapping the inner workflow; merges output | (GraphNode — delegates) |
| annex_iii_classify = `AnnexIIIClassifyNode` | inner | classify vs EU AI Act Annex III insurance taxonomy | INTERNAL |
| dual_reg_retrieve = `DualRegRetrieveNode` | inner | multi-corpus metadata-filtered retrieval (eu_ai_act / hoken_gyoho / fsa_mrm) | INTERNAL |
| gap_assess = `GapAssessNode` | inner | obligations vs system → structured gaps | INTERNAL |
| compliance_report = `ComplianceReportNode` | inner | cross-regulatory synthesis (locked output schema) | INTERNAL |
| post_process = `PostProcessNode` (OutputValidate) | outer | S-3 deterministic gate: disclaimer + kb_version present, no definitive verdict | ANONYMOUS |

### Data Flow (Cat 2 serialization)

Inner subgraph receives only the string `user_input` (from outer `validated_input`).
`PreProcessNode` serializes `{system_description, compliance_question}` to JSON;
`DualRegGraphNode.extract_input()` returns it; `AnnexIIIClassifyNode` reconstructs via
`json.loads`. Config (llm, retriever, top_k) reaches inner via `_parent_config()`.

### State Definition

| Field | Type | Purpose |
|-------|------|---------|
| system_description / compliance_question | `NotRequired[str]` | caller inputs |
| annex_iii_points / classification_rationale / high_risk | `NotRequired[...]` | classification result |
| retrieved_obligations | `NotRequired[dict]` | per-corpus obligation passages |
| gaps | `NotRequired[list[dict]]` | structured cross-regulatory gaps |
| compliance_report / kb_version | `NotRequired[...]` | final report + KB stamp |

**Output schema (locked):** `annex_iii_verdict{points, high_risk}`, `gaps[]{regulation,
reference, obligation, status, priority}`, `art11_checklist[]`, `hokengyoho_obligations[]`,
`disclaimer`, `kb_version`.

## Framework Utilization

- **S-1**: `required_trust_level` explicit on every node; INTERNAL on classification /
  retrieval / gap / report nodes; ANONYMOUS on validate/format. Agent default INTERNAL.
- **S-2**: framework `@final` PII scan + deterministic token/マイナンバー scan in `PreProcessNode.execute()`.
- **S-3**: framework `@final` credential scan + `_extra_security_gate_output()` on
  `PostProcessNode` (preservation + filter: disclaimer + kb_version present; no definitive verdict).
- **S-3 secrets**: `LLM_API_KEY` / `VECTOR_STORE_API_KEY` in `agent.yaml requires.secrets`;
  provisioned at entry via `bound_secrets`/`secrets_factory`. Never `os.environ`, never in state.
- **S-4**: every node emits ≥1 domain `emit_trace_event()`; GraphNode wrapper emits from
  `extract_input()` / `merge_output()`.

### Composition Pattern

- Cat 2 — outer `AgentBaseGraph` + `GraphNode` (`main`) + inner `BaseGraph`.
- Error propagation: `propagate` (inner errors surface as SubgraphError → fail fast);
  inner nodes also short-circuit on upstream ERROR.

## Import Isolation

- No Level 0 (`agenticstar`) imports; imports limited to `framework/`, `shared/`, `src/`.

## Design Decision Record

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| L1 base | AgentBaseGraph | multi-step dual-regulatory workflow, not autonomous loop |
| Composition | GraphNode + inner BaseGraph | Cat 2 requires GraphNode in `main` (gate-composition) |
| No definitive verdict | S-3 blocklist | advisory-only; legal determination requires counsel |
| Disclaimer + kb_version | S-3 preservation | traceability + safe-use guarantee on every answer |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=ins`, `agent_name=ins-c2-048`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. Both entry points build the client only when all three resolve and pass it in
as `config["llm"]`; when any is absent the key stays unset and the graph keeps its deterministic
path. The manifest declares the three secrets and the provider extra.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
