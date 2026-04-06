"""
Promoter Agent — Stage 8 of the SKILL FORGE pipeline.

Checks statistical confidence gates (CI lower >= 0.80, composite >= 8.5, κ >= 0.70),
writes skill files to generated_skills/, and updates the staging registry.
"""
import math
import json
from pathlib import Path
from google.adk.agents import Agent
from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
from tools.skill_forge_db import (
    init_db,
    get_best_skill_version_sync,
    get_battle_test_sync,
    stage_skill_sync,
    list_staged_skills_sync,
)

init_db()

GENERATED_SKILLS_ROOT = Path(__file__).parent.parent.parent.parent / "generated_skills"


def compute_promotion_gates(
    pass_rate: float,
    composite_score: float,
    judge_scores: list,
    n: int = 100,
) -> dict:
    """
    Compute all three promotion gates and return a gate report.

    Gates:
      1. CI lower bound >= 0.80 (95% confidence interval)
      2. composite_score >= 8.5
      3. Cohen's kappa >= 0.70 (judge agreement)

    judge_scores: list of 3 floats (0-10 scale, normalised to 0-1 for kappa)
    """
    z = 1.96
    margin = z * math.sqrt(pass_rate * (1.0 - pass_rate) / n) if n > 0 else 0.0
    ci_lower = round(max(0.0, pass_rate - margin), 4)
    ci_upper = round(min(1.0, pass_rate + margin), 4)

    kappa = _cohen_kappa_three_judges(judge_scores) if len(judge_scores) >= 2 else 0.0

    gate_ci = ci_lower >= 0.80
    gate_composite = composite_score >= 8.5
    gate_kappa = kappa >= 0.70

    return {
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "kappa": round(kappa, 4),
        "gate_ci": gate_ci,
        "gate_composite": gate_composite,
        "gate_kappa": gate_kappa,
        "all_gates_pass": gate_ci and gate_composite and gate_kappa,
    }


def _cohen_kappa_three_judges(scores: list) -> float:
    """
    Approximate Cohen's kappa for 3 judges by averaging pairwise kappas.
    Scores are 0-10; discretised into bins for agreement calculation.
    """
    if len(scores) < 2:
        return 0.0

    def pairwise_kappa(s1: float, s2: float) -> float:
        # Discretise into 3 bins: low (<5), medium (5-7.5), high (>7.5)
        def bin_score(s: float) -> int:
            if s < 5.0:
                return 0
            elif s <= 7.5:
                return 1
            else:
                return 2

        b1, b2 = bin_score(s1), bin_score(s2)
        p_observed = 1.0 if b1 == b2 else 0.0
        p_expected = 1.0 / 3.0  # uniform random agreement across 3 bins
        if p_expected == 1.0:
            return 1.0
        return (p_observed - p_expected) / (1.0 - p_expected)

    pairs = [(scores[i], scores[j]) for i in range(len(scores)) for j in range(i + 1, len(scores))]
    if not pairs:
        return 0.0
    return sum(pairwise_kappa(a, b) for a, b in pairs) / len(pairs)


def write_skill_files(
    skill_name: str,
    domain: str,
    skill_content: str,
    metadata: dict,
    test_cases: list,
    audit_content: str,
) -> str:
    """
    Write SKILL.md, metadata.json, test_suite.json, and AUDIT.md to
    generated_skills/{domain}/{skill-name}/.
    Returns the directory path as a string.
    """
    safe_domain = domain.lower().replace(" ", "-").replace("/", "-")[:40]
    safe_name = skill_name.lower().replace(" ", "-").replace("/", "-")[:60]
    skill_dir = GENERATED_SKILLS_ROOT / safe_domain / safe_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
    (skill_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (skill_dir / "test_suite.json").write_text(json.dumps(test_cases, indent=2), encoding="utf-8")
    (skill_dir / "AUDIT.md").write_text(audit_content, encoding="utf-8")

    return str(skill_dir)


INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are the Promoter Agent for the SKILL FORGE pipeline.

Your job is Stage 8: verify promotion gates, write skill files, and update the
staging registry.

## Input
You receive:
{
  "session_id": <int>,
  "skill_name": <str>,
  "domain": <str>,
  "department": <str>,
  "judge_scores": [<float>, <float>, <float>]  # from the 3 critics
}

## Process

1. Retrieve skill data:
   - Call get_best_skill_version_sync(session_id) → skill content + composite_score + version
   - Call get_battle_test_sync(session_id, version) → pass_rate + failure_breakdown + test_cases

2. Check promotion gates using compute_promotion_gates:
   - CI lower bound >= 0.80
   - composite_score >= 8.5
   - Cohen's kappa >= 0.70

3. Gate decision:

   a. All 3 gates pass → PROMOTE:
      - needs_review = False
      - Write skill files using write_skill_files
      - skill_id = "{domain}-{skill_name}" (normalised, hyphen-separated)

   b. composite >= 8.5 but CI or kappa fails → PROMOTE WITH REVIEW:
      - needs_review = True
      - Write skill files with review flag

   c. composite < 8.5 (should not reach here from iteration_agent normally):
      - needs_review = True
      - Write skill files with strong review flag

4. Build metadata.json:
   {
     "skill_id": <str>,
     "skill_name": <str>,
     "domain": <str>,
     "department": <str>,
     "composite_score": <float>,
     "scores": {"correctness": X, "robustness": X, "instruction_clarity": X, "domain_accuracy": X},
     "pass_rate": <float>,
     "ci_lower": <float>,
     "ci_upper": <float>,
     "kappa": <float>,
     "version": <int>,
     "needs_review": <bool>,
     "generated_at": <ISO timestamp>
   }

5. Build AUDIT.md following the spec format with composite scores, battle-test table,
   failure breakdown, and research citations.

6. Call stage_skill_sync(skill_id, skill_name, domain, department, file_path,
   composite_score, needs_review)

7. Return the FORGE SUMMARY:

```
SKILL FORGE SUMMARY
════════════════════════════════════════════
Skill:          {skill_name}
Domain:         {domain}
Staged at:      generated_skills/{path}/

── PIPELINE RESULTS ────────────────────────
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
Judge agreement:κ = {kappa}
Cases run:      100 (40 common / 30 edge /
                     20 adversarial / 10 regression)

── STATUS ──────────────────────────────────
Staged:         ✓ generated_skills/{path}/
Production:     Pending (0/5 runs needed)
Needs review:   {true/false}
════════════════════════════════════════════
```
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "thinking", "memory"])

promoter_agent = Agent(
    model=get_model(),
    name="promoter_agent",
    description=(
        "Checks CI gate (lower >= 0.80), composite >= 8.5, and kappa >= 0.70. "
        "Writes skill files and updates staging registry. Stage 8 of SKILL FORGE."
    ),
    instruction=INSTRUCTION,
    tools=[
        compute_promotion_gates,
        write_skill_files,
        get_best_skill_version_sync,
        get_battle_test_sync,
        stage_skill_sync,
        list_staged_skills_sync,
        *_mcp_tools,],
)
