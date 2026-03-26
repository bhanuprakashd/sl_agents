# SKILL FORGE: Autonomous Skill Generation & Battle-Testing Framework

**Date:** 2026-03-26
**Status:** Approved
**Author:** Claude (autonomous design session)

---

## Executive Summary

SKILL FORGE is a 12-agent multi-agent framework that generates battle-tested Claude Code skills from a single NLP sentence. It synthesizes domain expert knowledge through a parallel research swarm, drafts structured SKILL.md files, subjects them to a heterogeneous critic panel debate, adversarially red-teams 100 test cases, and iterates via GEPA reflective loops until composite quality score ≥ 8.5/10. Skills are staged in a `generated_skills/` registry and auto-promoted to production after 5 successful runs.

**Goal:** Generate skills that perform in the top 1% of human practitioners on a given task, with automated validation providing statistical confidence (95% CI) before promotion.

---

## Research Basis

Framework design is grounded in 2025-2026 frontier research:

| Technique | Source | Applied In |
|---|---|---|
| GEPA (reflective prompt evolution) | ICLR 2026 Oral | Iteration Agent loop |
| DSPy/MIPRO (instruction + demo joint optimization) | Stanford 2024 | Skill Drafter |
| A-HMAD (heterogeneous multi-agent debate) | ICLR 2025 | Critic Panel |
| Mixture-of-Agents (depth > breadth) | Together AI 2024 | Critic Panel |
| Reflexion (episodic memory + feedback) | MIT 2023 | Iteration Agent |
| Constitutional AI | Anthropic 2022 | Expert Synthesizer |
| G-Eval (LLM-as-judge + CoT) | Confident AI 2024 | All scoring |
| Voyager/SAGE (skill library + RL) | Princeton/2025 | Staging registry |
| OPRO (optimization by prompting) | DeepMind 2023 | Iteration Agent |
| Focused Chain-of-Thought | arXiv 2025 | Skill Drafter |

**Key research finding:** The gap between 75th and 99th percentile performance comes from three specific mechanisms: (1) iterative critique + reflection, (2) heterogeneous adversarial debate, and (3) systematic red-team battle-testing. This framework implements all three.

---

## System Architecture

```
INPUT: NLP sentence (user or agent)
"generate skill for: writing VC pitch decks"

STAGE 1: UNDERSTAND
┌─────────────────────────────────────────────────────┐
│ Intent Parser Agent                                  │
│ NLP → TaskSpec (domain, success criteria, scope)    │
└─────────────────────────────────────────────────────┘
                     ↓
STAGE 2: RESEARCH (3 parallel agents)
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ Domain       │ │ Benchmark    │ │ Technique        │
│ Researcher   │ │ Researcher   │ │ Researcher       │
│ (expert      │ │ (top 1%      │ │ (latest methods, │
│  knowledge)  │ │  outputs)    │ │  tools, papers)  │
└──────────────┘ └──────────────┘ └──────────────────┘
                     ↓
STAGE 3: SYNTHESIZE
┌─────────────────────────────────────────────────────┐
│ Expert Synthesizer Agent                             │
│ → Constitutional principles (5-8)                   │
│ → Gold standard examples (5-10)                     │
│ → Failure mode catalog                              │
└─────────────────────────────────────────────────────┘
                     ↓
STAGE 4: DRAFT
┌─────────────────────────────────────────────────────┐
│ Skill Drafter Agent (DSPy/GEPA pattern)             │
│ → Generates SKILL.md v0                             │
└─────────────────────────────────────────────────────┘
                     ↓
STAGE 5: CRITIQUE (3 parallel, A-HMAD debate)
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ Domain       │ │ Instruction  │ │ Edge Case        │
│ Expert Critic│ │ Quality      │ │ Critic           │
│ (is it true?)│ │ Critic       │ │ (what breaks it?)│
└──────────────┘ └──────────────┘ └──────────────────┘
                     ↓ composite ≥ 7.5
STAGE 6: BATTLE-TEST
┌─────────────────────────────────────────────────────┐
│ Red Team Agent                                       │
│ → 100 test cases: 40 common / 30 edge /             │
│   20 adversarial / 10 regression                    │
│ → BattleTestReport (pass rate, CI, failure map)     │
└─────────────────────────────────────────────────────┘
                     ↓
STAGE 7: ITERATE (GEPA reflection loop)
┌─────────────────────────────────────────────────────┐
│ Iteration Agent                                      │
│ while composite < 8.5 and iterations < 10:          │
│   reflect → patch → re-test → rollback if regress   │
└─────────────────────────────────────────────────────┘
                     ↓ composite ≥ 8.5
STAGE 8: PROMOTE
┌─────────────────────────────────────────────────────┐
│ Promoter Agent                                       │
│ → Statistical confidence gate (CI lower ≥ 0.80)    │
│ → Write to generated_skills/ staging registry       │
│ → Auto-promote to aass_agents/skills/ after 5 runs  │
└─────────────────────────────────────────────────────┘
```

---

## Agent Specifications

### Agent 1: Intent Parser

**Input:** Raw NLP string
**Output:** `TaskSpec` object

```json
{
  "task_name": "VC pitch deck writing",
  "domain": "venture capital / startup fundraising",
  "skill_type": "writing",
  "success_definition": "investor requests follow-up meeting",
  "scope_boundaries": "seed/series A, B2B SaaS focus",
  "existing_skill_path": null,
  "department": "generated",
  "priority": "high"
}
```

**Behaviour:**
- If ambiguous on domain or success_definition: ask ONE clarifying question
- If task matches existing skill: confirm upgrade vs. new parallel skill
- Log session to `skill_forge.db` (stage: intent)

---

### Agents 2-4: Research Swarm (parallel)

**Agent 2 — Domain Researcher**
- Extracts: expert mental models, decision heuristics, common mistakes, best practices
- Sources: papers, expert blogs, practitioner guides, case studies

**Agent 3 — Benchmark Researcher**
- Extracts: gold standard outputs, scoring rubrics, benchmark datasets, human baselines
- Sources: competitions, leaderboards, published audits

**Agent 4 — Technique Researcher**
- Extracts: relevant prompting techniques, tool integrations, structured reasoning schemas
- Sources: ArXiv, GitHub, ADK docs, existing SKILL.md patterns in codebase

**All 3 output:** `ResearchBundle` — structured findings with citations
**Failure handling:** Retry once if agent crashes; proceed with 2/3 bundles minimum

---

### Agent 5: Expert Synthesizer

**Input:** 3x `ResearchBundle`
**Output:** `ExpertBlueprint`

```json
{
  "constitutional_principles": ["5-8 positive, behavior-based rules"],
  "gold_examples": ["5-10 input/output pairs"],
  "failure_mode_catalog": ["known failure patterns with descriptions"],
  "success_criteria": ["measurable quality gates"],
  "domain_constraints": ["things skill must never do"]
}
```

**Technique:** Constitutional AI synthesis — extracts positive, behavior-based principles from cross-source expert consensus. Principles are framed as "do X" not "don't do Y."

---

### Agent 6: Skill Drafter

**Input:** `TaskSpec` + `ExpertBlueprint`
**Output:** `SKILL.md` v0

Generates complete SKILL.md following existing `aass_agents/skills/` format. Embeds:
- Constitutional principles as explicit instructions
- 2-3 gold examples as in-skill demonstrations (DSPy-style demo selection)
- Failure modes as explicit guards
- Focused Chain-of-Thought schema appropriate to task type (writing/research/analysis/coding/strategy)

**Draft-critique cycle:** Up to 3 cycles with Critic Panel before advancing to battle-test.

---

### Agents 7-9: Critic Panel (A-HMAD debate)

Three heterogeneous judges with distinct reasoning lenses:

**Agent 7 — Domain Expert Critic**
- Checks factual accuracy, completeness, missing expert knowledge, outdated techniques
- Output: domain score (1-10) + specific corrections

**Agent 8 — Instruction Quality Critic**
- Checks clarity, actionability, step ordering, example alignment
- Output: instruction score (1-10) + rewrite suggestions

**Agent 9 — Adversarial Edge Case Critic**
- Generates 10 adversarial scenarios, tests each against draft
- Output: robustness score (1-10) + failure scenarios list

**Debate resolution:**
- Critics share scores + reasoning
- If any two critics diverge by >2 points: one debate round, then re-score
- Composite < 7.5 → back to Skill Drafter with critique notes (max 3 cycles)
- Composite < 7.5 after 3 cycles → session flagged as `stalled`, user notified

---

### Agent 10: Red Team Agent

**Input:** `SKILL.md` + failure scenarios from critics
**Output:** `BattleTestReport`

**Test case distribution (100 total):**

| Category | Count | Purpose |
|---|---|---|
| Common | 40 | Verify baseline correctness on expected inputs |
| Edge | 30 | Verify graceful handling of boundary conditions |
| Adversarial | 20 | Verify robustness: conflicting premises, prompt injection, trick inputs |
| Regression | 10 | Known failure modes from ExpertBlueprint + prior iteration failures |

**Test case structure:**
```json
{
  "case_id": "tc_042",
  "category": "adversarial",
  "input": "...",
  "expected_behavior": "...",
  "failure_signal": "...",
  "judge_rubric": "correctness + domain_accuracy"
}
```

---

### Agent 11: Iteration Agent (GEPA loop)

**Input:** `SKILL.md` + `BattleTestReport` + critic notes
**Output:** `SKILL.md` vN (improved)

```
while composite_score < 8.5 and iterations < 10:
    reflect: "Why did cases X, Y, Z fail? What specific instruction change fixes this?"
    patch: targeted edit to SKILL.md (not full rewrite)
    re-test: run red team on worst_cases only (20 cases, fast loop)
    log: new version to skill_versions
    if score regresses > 0.5 points: rollback to previous version
    iterations += 1

if best_score < 8.5 after 10 iterations:
    promote best version with needs_review: true
```

**Technique:** GEPA reflective evolution — reflects on *why* failure occurred, not random mutation. Proven highest-performing optimizer (ICLR 2026 Oral).

---

### Agent 12: Promoter Agent

**Input:** `SKILL.md` vFinal + `BattleTestReport`
**Output:** Staging registry entry

**Statistical confidence gate:**
```python
# CI lower bound must be ≥ 0.80
pass_rate = passed_cases / 100
margin = 1.96 * sqrt(pass_rate * (1 - pass_rate) / 100)
ci_lower = pass_rate - margin

# Judge agreement gate
kappa = cohen_kappa(judge1_scores, judge2_scores, judge3_scores)
# Required: kappa ≥ 0.70

# Both gates must pass
if ci_lower >= 0.80 and composite >= 8.5 and kappa >= 0.70:
    promote_to_staging()
```

**Staging output:**
```
generated_skills/{domain}/{skill-name}/
├── SKILL.md          # final version
├── metadata.json     # scores, versions, timestamps, citations
├── test_suite.json   # all 100 cases (used for regression on future edits)
└── AUDIT.md          # human-readable audit trail
```

**Production promotion:** Auto-triggered when `staging_registry.production_runs ≥ 5` AND average reflection_agent score ≥ 7.0. Demotes back to staging if 2 consecutive production runs score < 6.0.

---

## Scoring System

### Composite Formula

```
composite = (
    0.35 × correctness_score      # does it do the task right?
    0.25 × robustness_score       # does it handle edge cases?
    0.20 × instruction_clarity    # is it unambiguous?
    0.20 × domain_accuracy        # is expert knowledge correct?
)
```

### Promotion Gates

| Gate | Threshold | Where |
|---|---|---|
| Draft → Critique pass | composite ≥ 7.5 | After Critic Panel |
| Critique → Battle-test | composite ≥ 7.5 | After 3 draft cycles max |
| Battle-test → Staging | composite ≥ 8.5 + CI lower ≥ 0.80 + κ ≥ 0.70 | After Iteration loop |
| Staging → Production | 5 runs, avg ≥ 7.0 | Tracked by reflection_agent |

### G-Eval Rubric Per Dimension

**Correctness (0.35):** Judge CoT → extract claims → verify against domain → check logical consistency → verify conclusions follow from evidence

**Robustness (0.25):** Judge CoT → test 5 adversarial variants → check graceful degradation → verify boundary handling → check missing/ambiguous input handling

**Instruction Clarity (0.20):** Judge CoT → read as first-time user → identify ambiguous verbs → verify every step executable → verify example alignment

**Domain Accuracy (0.20):** Judge CoT → compare vs. current best practices → check for outdated techniques → verify terminology → verify top-1% expert knowledge

### Multi-Judge Architecture

```
Skill Output
     │
     ├──→ Judge 1 (Domain Expert persona)
     ├──→ Judge 2 (End User persona)         → 3 independent scores
     └──→ Judge 3 (Adversarial Critic persona)
                │
                ▼
     Cohen's κ check
          κ ≥ 0.70 → average scores
          κ < 0.70 → one debate round → re-score
```

---

## State Management

Single `skill_forge.db` (SQLite, mirrors `evolution.db` pattern):

```
skill_forge.db
├── forge_sessions         # session_id, task_spec, current_stage, status
├── research_bundles       # session_id, researcher_type, findings, citations
├── skill_versions         # session_id, version, skill_content, composite_score
├── battle_test_results    # session_id, version, pass_rate, failure_breakdown
└── staging_registry       # skill_id, name, department, file_path, production_runs
```

**Resume semantics:** If any agent crashes mid-pipeline, next invocation reads `current_stage` from `forge_sessions` and resumes from last committed stage. No work is lost.

---

## Integration with Existing Systems

### Autoresearcher Loop (sibling, not replacement)

```
reflection_agent scores production output
        │
        ├──→ evolution.db (autoresearcher reads → improves agent instructions)
        └──→ skill_forge.db staging_registry.production_runs++
             (SKILL FORGE reads → tracks promotion gates)
```

### Trigger Interface

**Direct user invocation:**
```
/forge "writing VC pitch decks"
```

**Agent-to-agent tool call:**
```python
forge_skill(
    request="generate skill for: executive briefing documents",
    priority="high",
    department="product"
)
```

**NLP trigger phrases:** "generate skill for", "create a skill that", "build me a skill to", "forge skill"

---

## File Structure

```
sl_agents/
├── aass_agents/
│   ├── agents/skill_forge/
│   │   ├── intent_parser_agent.py
│   │   ├── research_swarm_agent.py
│   │   ├── expert_synthesizer_agent.py
│   │   ├── skill_drafter_agent.py
│   │   ├── critic_panel_agent.py
│   │   ├── red_team_agent.py
│   │   ├── iteration_agent.py
│   │   └── promoter_agent.py
│   ├── tools/
│   │   └── skill_forge_db.py
│   └── skills/skill-forge/
│       └── SKILL.md
│
└── generated_skills/
    ├── _registry.json
    └── {domain}/{skill-name}/
        ├── SKILL.md
        ├── metadata.json
        ├── test_suite.json
        └── AUDIT.md
```

---

## Failure Handling

| Failure | Behaviour |
|---|---|
| Research agent crashes | Retry once; proceed with 2/3 bundles |
| Critic composite < 7.5 after 3 drafts | Flag `stalled`, surface to user |
| Iteration hits 10 loops without ≥ 8.5 | Promote best version with `needs_review: true` |
| Composite < 7.0 after all iterations | Do not stage; surface to user with explanation |
| Production run scores < 6.0 (2 consecutive) | Demote to staging; re-trigger iteration agent |

---

## AUDIT.md Format

```markdown
# Skill Audit: {skill_name}
Generated: {timestamp}  |  Version: v{N}  |  Iterations: {N}

## Composite Score: {X} / 10
| Dimension           | Score | Weight | Weighted |
|---------------------|-------|--------|---------|
| Correctness         | X.X   | 0.35   | X.XX    |
| Robustness          | X.X   | 0.25   | X.XX    |
| Instruction Clarity | X.X   | 0.20   | X.XX    |
| Domain Accuracy     | X.X   | 0.20   | X.XX    |

## Battle-Test Results
- Total cases: 100
- Pass rate: X% (CI: X-X%, 95% confidence)
- Judge agreement: κ = X.XX

## Failure Breakdown
| Category    | Cases | Passed | Failed |
|-------------|-------|--------|--------|
| Common      | 40    | X      | X      |
| Edge        | 30    | X      | X      |
| Adversarial | 20    | X      | X      |
| Regression  | 10    | X      | X      |

## Known Limitations
- [Specific edge cases handled imperfectly]

## Research Sources
- [Citations from Research Swarm]
```

---

## Forge Summary Output

```
SKILL FORGE SUMMARY
════════════════════════════════════════════
Skill:          {skill_name}
Domain:         {domain}
Staged at:      generated_skills/{path}/

── PIPELINE RESULTS ────────────────────────
Research:       3 bundles ({N} sources)
Draft cycles:   {N}
Iterations:     {N} (GEPA loop)

── FINAL SCORES ────────────────────────────
Correctness:    {score}/10
Robustness:     {score}/10
Clarity:        {score}/10
Domain Accuracy:{score}/10
COMPOSITE:      {score}/10

── BATTLE-TEST ─────────────────────────────
Pass rate:      {N}% (CI: {low}-{high}%, 95%)
Judge agreement:κ = {score}
Cases run:      100 (40 common / 30 edge /
                     20 adversarial / 10 regression)

── STATUS ──────────────────────────────────
Staged:         ✓ generated_skills/{path}/
Production:     Pending ({runs}/5 runs needed)
Needs review:   {true/false}
════════════════════════════════════════════
```

---

## Open Questions

1. Should the research swarm use web search (live sources) or only internal codebase + cached knowledge? Live search gives fresher data but adds latency and cost.
2. Should the `/forge` skill be available globally (like autoresearcher) or department-scoped?
3. What is the maximum acceptable latency per skill generation run? (Estimate: 15-25 min for full pipeline with 100 test cases.)
