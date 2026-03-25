# Engineering & Research Departments — Design Specification

> **Status:** Approved for implementation
> **Date:** 2026-03-25
> **Extends:** `docs/superpowers/specs/2026-03-24-sota-autonomous-supervisor-design.md`

**Goal:** Add Engineering (pipeline & systems builders) and Research & Development departments to the existing sales-adk-agents multi-agent system, following the established orchestrator/sub-agent pattern.

**Architecture:** Two new orchestrators wired into company_orchestrator. Engineering owns full-spectrum pipeline and systems building (data, AI/ML, toolchains, integrations, platform). Research & Development owns R&D across scientific, market intelligence, and user research domains. Both follow the existing ADK Agent pattern with reflection loops, memory protocol, and supervisor layer integration.

**Tech Stack:** Python 3.11+, Google ADK, SQLite (supervisor layer), existing tools (github_tools, code_gen_tools, research_tools, http_tools)

---

## 1. Existing System Context

The system (`sales-adk-agents`) already has:

- `company_orchestrator` — top-level router
- `sales_orchestrator` + 7 specialist agents (Sales dept)
- `marketing_orchestrator` + 6 specialist agents (Marketing dept)
- `product_orchestrator` + 7 specialist agents (Product dept)
- `reflection_agent` factory (`make_reflection_agent()`) — each orchestrator gets its own instance
- Supervisor layer: `tools/supervisor.py` with event log, loop guard, circuit breaker, staleness registry, DLQ
- Memory tools: `tools/memory_tools.py` with `save_agent_output`, `recall_past_outputs`, `save_deal_context`, `recall_deal_context`
- Existing tools: `github_tools.py`, `code_gen_tools.py`, `research_tools.py`, `http_tools.py`, `memory_tools.py`

**Pattern every team follows:**

- One orchestrator agent with `sub_agents=[]`, `tools=[]`, `instruction=INSTRUCTION`
- Each orchestrator gets `make_reflection_agent()` — never shares singleton
- Specialist agents: `Agent(model=MODEL, name=..., description=..., instruction=..., tools=[...])`
- Memory protocol: recall at session start, save after each agent completes
- Reflection loop: invoke after sub-agent, quality check, re-invoke if needed (max 2 cycles)
- Autonomous execution: no user confirmation between steps; pause only for genuine blockers

---

## 2. Target Architecture

Three new departments added to `company_orchestrator`:

```
company_orchestrator
├── sales_orchestrator        (existing)
├── marketing_orchestrator    (existing)
├── product_orchestrator      (existing)
├── engineering_orchestrator  ← NEW
├── research_orchestrator     ← NEW
└── qa_orchestrator           ← NEW
```

---

## 3. Engineering Department — Pipeline & Systems Builders

### 3.1 Identity

Takes components (models, APIs, tools, data sources) and assembles them into working pipelines and integrated systems. Full-spectrum: data pipelines, AI/ML pipelines, software toolchains, integration layers, deployment automation.

### 3.2 Orchestrator Routing Logic

| Trigger keywords | Delegate to |
|---|---|
| "architecture" / "design system" / "solution design" | `solutions_architect_agent` |
| "data pipeline" / "ETL" / "streaming" / "feature store" | `data_engineer_agent` |
| "ML pipeline" / "training" / "inference" / "model serving" | `ml_engineer_agent` |
| "toolchain" / "build system" / "compiler" / "EDA" / "embedded build" | `systems_engineer_agent` |
| "integrate" / "connect" / "API gateway" / "middleware" / "service mesh" | `integration_engineer_agent` |
| "deploy" / "infrastructure" / "IaC" / "container" / "CI/CD platform" | `platform_engineer_agent` |
| "test pipeline" / "validate integration" / "pipeline smoke test" / "pipeline regression" | `sdet_agent` |

> **sdet_agent scope (Engineering):** Pipeline and infrastructure testing only. Tests data pipelines, ML pipelines, EDA toolchains, and service integrations. It does NOT test product features or application-level flows — those belong to `test_automation_engineer_agent` in the QA department.

### 3.3 Specialist Agents

| Agent file | Real-world title | Tools | Key outputs |
|---|---|---|---|
| `solutions_architect_agent.py` | Solutions Architect | `code_gen_tools`, `research_tools`, `engineering_tools.create_pipeline_spec` | System design docs, architecture decision records, component diagrams |
| `data_engineer_agent.py` | Data Engineer | `code_gen_tools`, `github_tools`, `engineering_tools.create_pipeline_spec`, `engineering_tools.get_pipeline_status` | ETL pipelines, streaming jobs, feature store schemas |
| `ml_engineer_agent.py` | Machine Learning Engineer | `code_gen_tools`, `github_tools`, `engineering_tools.create_pipeline_spec`, `engineering_tools.get_pipeline_status` | Training pipelines, eval frameworks, inference configs |
| `systems_engineer_agent.py` | Systems Engineer | `code_gen_tools`, `github_tools`, `engineering_tools.create_pipeline_spec` | EDA toolchains, compiler pipelines, embedded build systems |
| `integration_engineer_agent.py` | Integration Engineer | `code_gen_tools`, `http_tools`, `engineering_tools.log_integration`, `engineering_tools.get_pipeline_status` | API connectors, middleware, service mesh configs, data contracts |
| `platform_engineer_agent.py` | Platform Engineer | `github_tools`, `code_gen_tools`, `engineering_tools.get_pipeline_status`, `engineering_tools.log_integration` | IaC scripts, CI/CD platform configs, container orchestration |
| `sdet_agent.py` | Pipeline Test Engineer | `code_gen_tools`, `github_tools`, `engineering_tools.get_pipeline_status` | Pipeline validation reports, integration test plans, pipeline smoke test results |

### 3.4 New Tool File: `tools/engineering_tools.py`

Three functions to expose to engineering agents:

- `create_pipeline_spec(name, stages, inputs, outputs)` — returns a structured pipeline definition dict persisted to the session store
- `log_integration(system_a, system_b, protocol, status)` — appends an entry to the integration registry
- `get_pipeline_status(pipeline_name)` — returns the current build/run status snapshot for the named pipeline

### 3.5 Engineering Card

The `engineering_orchestrator` maintains an Engineering Card throughout the session and prints it after each specialist completes.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENGINEERING CARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
System:      [Name of pipeline/system being built]
Type:        [Data Pipeline / AI Pipeline / Toolchain / Integration / Platform]
Stack:       [Technologies involved]
Status:      [Design / Building / Testing / Complete]
Last Action: [What was done]
Next Step:   [Action + owner]
Open Issues: [Blockers or gaps]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Completed: [A] Architecture  [D] Data  [M] ML
           [S] Systems       [I] Integration  [P] Platform  [T] Tests
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3.6 Reflection Triggers

Reflection is always run for:

- Architecture designs (output from `solutions_architect_agent`)
- Integration specs before implementation (output from `integration_engineer_agent`)
- SDET test plans for critical pipelines (output from `sdet_agent`)

---

## 4. Research & Development Department

### 4.1 Identity

Generates knowledge across three domains — scientific/academic R&D, market/competitive intelligence, and user/product research. Outputs: research papers, feasibility assessments, experiment results, competitive briefs, user insights.

### 4.2 Orchestrator Routing Logic

| Trigger keywords | Delegate to |
|---|---|
| "literature review" / "paper" / "hypothesis" / "experiment design" | `research_scientist_agent` |
| "model architecture" / "SOTA" / "benchmark" / "AI research" | `ml_researcher_agent` |
| "feasibility" / "can we build" / "research to product" / "applied" | `applied_scientist_agent` |
| "A/B test" / "metrics" / "statistical analysis" / "experiment" | `data_scientist_agent` |
| "competitor" / "market" / "industry trend" / "patent" / "battle card" | `competitive_analyst_agent` |
| "user interview" / "usability" / "persona" / "customer insight" | `user_researcher_agent` |
| "summarise findings" / "research brief" / "what do we know" | `knowledge_manager_agent` |

### 4.3 Specialist Agents

| Agent file | Real-world title | Tools | Key outputs |
|---|---|---|---|
| `research_scientist_agent.py` | Research Scientist | `research_tools` | Literature reviews, hypothesis docs, experiment designs, research papers |
| `ml_researcher_agent.py` | Machine Learning Researcher | `research_tools`, `code_gen_tools` | SOTA benchmarks, novel architecture proposals, training experiment plans |
| `applied_scientist_agent.py` | Applied Scientist | `research_tools`, `code_gen_tools` | Feasibility reports, research-to-product opportunity briefs |
| `data_scientist_agent.py` | Data Scientist | `code_gen_tools`, `research_tools` | Statistical analyses, A/B test designs, experiment reports, metric definitions |
| `competitive_analyst_agent.py` | Competitive Intelligence Analyst | `research_tools` | Competitor profiles, market trend reports, patent landscape, battle cards |
| `user_researcher_agent.py` | UX Researcher | `research_tools` | Interview guides, usability reports, persona documents, customer insight briefs |
| `knowledge_manager_agent.py` | Research Program Manager | `research_tools` | Research briefs, internal knowledge base entries, cross-domain synthesis reports |

### 4.4 Research Card

The `research_orchestrator` maintains a Research Card throughout the session and prints it after each specialist completes.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCH CARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Study:       [Research topic / question]
Domain:      [Academic / Market / Product Research]
Status:      [Scoping / Active / Synthesis / Complete]
Key Finding: [Latest insight]
Last Action: [What was done]
Next Step:   [Action + owner]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Completed: [RS] Research Scientist  [ML] ML Researcher
           [AS] Applied Scientist   [DS] Data Scientist
           [CI] Competitive Intel   [UX] User Research  [KM] Knowledge Mgr
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 4.5 Reflection Triggers

Reflection is always run for:

- Research synthesis outputs (output from `knowledge_manager_agent`)
- Competitive intelligence briefs before sharing with Sales/Marketing (output from `competitive_analyst_agent`)
- Feasibility assessments that will drive Product roadmap decisions (output from `applied_scientist_agent`)

---

## 5. QA & Testing Department

### 5.1 Identity

Owns quality across the entire product and engineering lifecycle. Tests products, pipelines, and integrations before they reach production. Modelled after FAANG QA practices — Google's Test Engineering team, Meta's QA platform, Amazon's Builder Tools testing, Netflix's chaos engineering.

### 5.2 Orchestrator Routing Logic

`qa_orchestrator` routes all testing and quality tasks.

| Trigger keywords | Delegate to |
|---|---|
| "automate tests" / "write test suite" / "regression" / "CI test" | `test_automation_engineer_agent` |
| "load test" / "performance" / "benchmark" / "stress test" / "latency" | `performance_engineer_agent` |
| "security test" / "pen test" / "vulnerability" / "OWASP" / "fuzz" | `security_tester_agent` |
| "manual QA" / "test case" / "bug triage" / "acceptance testing" / "UAT" | `qa_engineer_agent` |
| "test strategy" / "test plan" / "test framework" / "quality gates" | `test_architect_agent` |
| "chaos" / "failure injection" / "resilience test" / "fault tolerance" | `chaos_engineer_agent` |

### 5.3 Specialist Agents

| Agent file | Real-world title | Tools | Key outputs |
|---|---|---|---|
| `test_architect_agent.py` | Test Architect | `code_gen_tools`, `research_tools` | Test strategy docs, quality gate definitions, test framework designs |
| `test_automation_engineer_agent.py` | Automation Test Engineer | `code_gen_tools`, `github_tools` | Automated test suites, CI test configs, API tests, UI tests, regression frameworks |
| `performance_engineer_agent.py` | Performance Engineer | `code_gen_tools`, `github_tools` | Load test scripts, performance reports, benchmark baselines |
| `security_tester_agent.py` | Security Test Engineer | `code_gen_tools`, `research_tools` | Penetration test reports, OWASP coverage, fuzz test results |
| `qa_engineer_agent.py` | QA Engineer | `code_gen_tools` | Test case libraries, bug reports, UAT sign-off docs |
| `chaos_engineer_agent.py` | Chaos Engineer | `code_gen_tools`, `github_tools` | Chaos experiment designs, resilience reports, failure injection scripts |

> **test_automation_engineer_agent scope (QA):** Application-level test automation only. Tests product features, APIs, UI flows, and CI regression gates. It does NOT test pipeline infrastructure — that belongs to `sdet_agent` in the Engineering department.
>
> **Routing distinction:**
> - `sdet_agent` (Engineering): "test pipeline" / "validate integration" / "pipeline smoke test" / "pipeline regression"
> - `test_automation_engineer_agent` (QA): "automate tests" / "write test suite" / "API test" / "UI test" / "CI test" / "regression suite"

### 5.4 QA Card

The `qa_orchestrator` maintains a QA Card throughout the session and prints it after each specialist completes.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA CARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Target:      [Product / Pipeline / Service under test]
Test Type:   [Functional / Performance / Security / Chaos]
Coverage:    [X% automated / Y test cases]
Status:      [Planning / Active / Complete / Blocked]
Last Defect: [Severity + summary]
Next Gate:   [Quality gate + date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Completed: [TA] Architecture  [AU] Automation  [PE] Performance
           [SE] Security      [QA] Manual QA   [CH] Chaos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 5.5 Reflection Triggers

Reflection is always run for:

- Security test reports before sharing with Engineering/Product (output from `security_tester_agent`)
- Chaos experiment results before sharing with Engineering/Product (output from `chaos_engineer_agent`)

---

## 6. Updated `company_orchestrator` Routing

Add the following entries to the existing routing logic in `agents/company_orchestrator_agent.py`:

| Trigger keywords | Delegate to |
|---|---|
| "build pipeline" / "integrate" / "deploy" / "architecture" / "toolchain" / "ML pipeline" | `engineering_orchestrator` |
| "test pipeline" / "validate integration" / "pipeline smoke test" | `engineering_orchestrator` (handled by `sdet_agent` internally) |
| "research" / "literature review" / "competitor" / "market analysis" / "user research" / "A/B test" / "feasibility" | `research_orchestrator` |
| "test [product feature]" / "UAT" / "acceptance test" | `product_orchestrator` (handled by `qa_agent` internally) |
| "performance test" / "load test" / "security test" / "chaos test" / "regression suite" / "test strategy" | `qa_orchestrator` |
| "automate tests" / "write test suite" / "API test" / "UI test" / "CI test" | `qa_orchestrator` (handled by `test_automation_engineer_agent` internally) |

> **IMPORTANT — `company_orchestrator` identity update:** The `INSTRUCTION` string in `agents/company_orchestrator_agent.py` MUST be updated:
> 1. Change identity from "GTM Orchestrator coordinating Sales and Marketing" to "Company Orchestrator coordinating six departments: Sales, Marketing, Product, Engineering, Research & Development, and QA & Testing".
> 2. Update the "Your Teams" table in the instruction to list all 6 orchestrators with their domain summaries:
>
> | Orchestrator | Domain |
> |---|---|
> | `sales_orchestrator` | Revenue generation: prospecting, outreach, deal management, closing |
> | `marketing_orchestrator` | Demand generation: campaigns, content, SEO, brand, analytics |
> | `product_orchestrator` | Product lifecycle: roadmap, design, engineering, release, product QA |
> | `engineering_orchestrator` | Pipeline & systems: data, ML, toolchain, integration, platform, pipeline testing |
> | `research_orchestrator` | Knowledge generation: academic R&D, market intelligence, user research |
> | `qa_orchestrator` | Company-wide quality: application regression, performance, security, chaos |

> **QA routing disambiguation — three-level hierarchy:**
>
> | QA Layer | Owner | Scope |
> |---|---|---|
> | `qa_agent` (Product team) | `product_orchestrator` | Product-level QA: tests product features built by the product team. NOT routed through `qa_orchestrator`. |
> | `sdet_agent` (Engineering team) | `engineering_orchestrator` | Pipeline and infrastructure testing: data pipelines, ML pipelines, EDA toolchains, and service integrations. |
> | `qa_orchestrator` (QA & Testing dept) | `company_orchestrator` | Company-wide quality: application regression, performance, security testing, chaos engineering. Separate from product QA and pipeline QA. |
>
> Routing rules at `company_orchestrator` level:
> - "test [product feature]" / "UAT" / "acceptance test" → `product_orchestrator` (qa_agent handles internally)
> - "test pipeline" / "validate integration" / "pipeline smoke test" → `engineering_orchestrator` (sdet_agent handles internally)
> - "performance test" / "load test" / "security test" / "chaos test" / "regression suite" / "test strategy" → `qa_orchestrator`

All three new orchestrators (`engineering_orchestrator`, `research_orchestrator`, `qa_orchestrator`) are added to `sub_agents=[]` in the `company_orchestrator` definition alongside the three existing orchestrators.

---

## 7. File Map

### 7.1 New Agent Files

```
agents/engineering_orchestrator_agent.py
agents/solutions_architect_agent.py
agents/data_engineer_agent.py
agents/ml_engineer_agent.py
agents/systems_engineer_agent.py
agents/integration_engineer_agent.py
agents/platform_engineer_agent.py
agents/sdet_agent.py
agents/research_orchestrator_agent.py
agents/research_scientist_agent.py
agents/ml_researcher_agent.py
agents/applied_scientist_agent.py
agents/data_scientist_agent.py
agents/competitive_analyst_agent.py
agents/user_researcher_agent.py
agents/knowledge_manager_agent.py
agents/qa_orchestrator_agent.py
agents/test_architect_agent.py
agents/test_automation_engineer_agent.py
agents/performance_engineer_agent.py
agents/security_tester_agent.py
agents/qa_engineer_agent.py
agents/chaos_engineer_agent.py
```

Total: 23 new agent files (3 orchestrators + 20 specialists).

### 7.2 New Tool Files

```
tools/engineering_tools.py
```

### 7.3 Modified Files

```
agents/company_orchestrator_agent.py  — add engineering, research, and qa orchestrators to sub_agents and routing
tools/supervisor_db.py                — add TTL entries for 20 new agents in AGENT_TTL_DAYS
```

### 7.4 Unchanged Files

- All existing agent files
- `tools/supervisor.py`, `tools/memory_tools.py`, `shared/memory_store.py`
- All existing tool files except where noted above

---

## 8. TTL Entries for New Agents (`supervisor_db.py`)

Add to `AGENT_TTL_DAYS` dict:

> **TTL key naming convention:** All TTL keys use the agent's `name` attribute exactly as defined in the Agent constructor (e.g., `name='solutions_architect_agent'`). Call sites must pass `callback_context.agent_name` directly — never strip the `_agent` suffix or use Python variable names.

### Engineering Agents

| Agent | TTL | Rationale |
|---|---|---|
| `engineering_orchestrator` | `None` | Router, never cached |
| `solutions_architect_agent` | `float("inf")` | Architecture decisions are manually invalidated, not time-based |
| `data_engineer_agent` | `None` | Pipeline builds are per-run |
| `ml_engineer_agent` | `None` | Pipeline builds are per-run |
| `systems_engineer_agent` | `float("inf")` | Toolchain designs are stable until explicitly changed |
| `integration_engineer_agent` | `None` | Integrations are per-run |
| `platform_engineer_agent` | `float("inf")` | Platform configs are stable until explicitly changed |
| `sdet_agent` | `None` | Test runs are per-run |

### Research Agents

| Agent | TTL (days) | Rationale |
|---|---|---|
| `research_orchestrator` | `None` | Router, never cached |
| `research_scientist_agent` | `30` | Academic findings are stable for ~a month |
| `ml_researcher_agent` | `14` | SOTA moves fast; refresh every two weeks |
| `applied_scientist_agent` | `14` | Feasibility is re-assessed frequently |
| `data_scientist_agent` | `7` | Metrics and experiment results change weekly |
| `competitive_analyst_agent` | `7` | Market landscape moves fast |
| `user_researcher_agent` | `30` | User insights are stable for ~a month |
| `knowledge_manager_agent` | `30` | Research briefs are stable for ~a month |

### QA & Testing Agents

| Agent | TTL | Rationale |
|---|---|---|
| `qa_orchestrator` | `None` | Router, never cached |
| `test_architect_agent` | `float("inf")` | Test strategy is stable until changed |
| `test_automation_engineer_agent` | `None` | Test runs are per-run |
| `performance_engineer_agent` | `7` | Performance baselines refresh weekly |
| `security_tester_agent` | `7` | Security posture changes frequently |
| `qa_engineer_agent` | `None` | QA runs are per-run |
| `chaos_engineer_agent` | `None` | Chaos experiments are per-run |

---

## 9. Implementation Notes

### Memory Protocol (all three departments)

Session-start tool calls per orchestrator:
- `engineering_orchestrator`: `recall_past_outputs(system_name)` → `get_pipeline_status(pipeline_name)`
- `research_orchestrator`: `recall_past_outputs(study_topic)` — no additional tool
- `qa_orchestrator`: `recall_past_outputs(target_system)` — no additional tool

Note: `list_active_deals()` is NOT applicable to any of these three orchestrators — omit it. Use `recall_past_outputs` only.

After each specialist agent completes, all three orchestrators call `save_agent_output` with agent name, task, and result.

### Reflection Loop (both departments)

Each orchestrator instantiates its own `make_reflection_agent()` — never a shared singleton. The loop:

1. Invoke specialist sub-agent
2. Pass output to reflection agent for quality check
3. If reflection flags issues, re-invoke specialist with feedback (max 2 cycles)
4. Proceed to next step after second cycle regardless

### Autonomous Execution

Both orchestrators run autonomously end-to-end. They pause only for genuine blockers (missing credentials, ambiguous requirements that cannot be inferred). No user confirmation is required between sub-agent steps.

### Engineering Tools Availability

`engineering_tools.py` functions are available to the `engineering_orchestrator` and can be passed selectively to specialist agents that need pipeline/integration state (e.g., `integration_engineer_agent` uses `log_integration`; `platform_engineer_agent` uses `get_pipeline_status`).

### Cross-Department Handoffs

- `research_orchestrator` → `product_orchestrator`: feasibility assessments and user research insights flow into product roadmap decisions
- `research_orchestrator` → `sales_orchestrator` / `marketing_orchestrator`: competitive intelligence briefs are always reflection-checked before sharing
- `engineering_orchestrator` → `product_orchestrator`: architecture decision records inform product technical feasibility
- `qa_orchestrator` → `engineering_orchestrator` / `product_orchestrator`: quality gate sign-offs and defect reports are reflection-checked before sharing
- All handoffs go through `company_orchestrator` routing; departments do not call each other directly

**Research → Sales (Competitive Intelligence):** `competitive_analyst_agent` is the authoritative source for competitor profiles, market trends, and battle cards. `lead_researcher_agent` in Sales consumes these outputs rather than generating its own competitive research. When `lead_researcher_agent` needs competitor context, it should trigger `competitive_analyst_agent` via the `company_orchestrator`.

---

## 10. FAANG Alignment

The department structure mirrors how leading tech companies organise at scale:

| Department | FAANG Reference |
|---|---|
| **Sales** | Salesforce model — SDRs, AEs, RevOps, Deal Desk |
| **Marketing** | HubSpot/Google model — Demand Gen, Campaign, Content, SEO, Brand, Analytics |
| **Product** | Amazon PRFAQ model — PM, Principal Architect, SWE, Frontend, DB, Release, QA |
| **Engineering** | Netflix/Stripe model — Solutions Architect, Data Eng, ML Eng, Systems Eng, Integration Eng, Platform Eng, SDET |
| **Research & Development** | Google Research/Amazon Science model — Research Scientist, ML Researcher, Applied Scientist, Data Scientist, Competitive Intel, UX Researcher, Research Program Manager |
| **QA & Testing** | Google Test Engineering + Netflix Chaos Engineering model — Test Architect, SDET, Performance Engineer, Security Tester, QA Engineer, Chaos Engineer |

**Key FAANG principles embedded:**
- **Amazon "You Build It, You Run It"** — Engineering agents own their pipeline outputs end-to-end
- **Google Launch Review** — QA `test_architect_agent` defines quality gates before any pipeline goes live
- **Netflix Chaos Engineering** — `chaos_engineer_agent` proactively injects failures to find weaknesses
- **Meta's Applied Science model** — `applied_scientist_agent` bridges Research and Engineering
- **Stripe API Review culture** — `integration_engineer_agent` enforces interface contracts before connecting systems
- **Amazon PRFAQ** — Product team starts from customer outcomes, not technical specs
