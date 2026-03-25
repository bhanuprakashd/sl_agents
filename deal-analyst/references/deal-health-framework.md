# Deal Health Framework

## Health Score Dimensions (Score 1–5 each, max 25)

### 1. Activity Recency
| Last Touch | Score |
|---|---|
| < 3 days ago | 5 |
| 3–7 days ago | 4 |
| 7–14 days ago | 3 |
| 14–21 days ago | 2 |
| > 21 days ago | 1 |

### 2. Stage Progression Velocity
| Status | Score |
|---|---|
| Moved forward this week | 5 |
| Moving at or faster than avg pace | 4 |
| At avg pace | 3 |
| 1.5× avg time in stage | 2 |
| 2× or more avg time in stage | 1 |

### 3. Stakeholder Coverage
| Status | Score |
|---|---|
| Economic buyer + champion engaged | 5 |
| Champion confirmed, EB identified but not engaged | 4 |
| Multiple contacts, unclear EB | 3 |
| Single contact only (single-threaded) | 2 |
| No confirmed contact | 1 |

### 4. Timeline Alignment
| Status | Score |
|---|---|
| Close date confirmed by prospect recently | 5 |
| Close date aligns with deal stage naturally | 4 |
| Close date plausible but unconfirmed | 3 |
| Close date seems optimistic vs. stage | 2 |
| Close date already passed / clearly wrong | 1 |

### 5. Next Step Clarity
| Status | Score |
|---|---|
| Specific next step with date booked | 5 |
| Next step defined, not yet scheduled | 4 |
| Vague next step ("will follow up") | 3 |
| No next step recorded | 2 |
| Deal is stalled with no agreed path | 1 |

---

## Health Score Bands

| Total Score | Rating | Action |
|---|---|---|
| 21–25 | Healthy | Monitor, keep momentum |
| 15–20 | Caution | Manager review, coach rep |
| 8–14 | At Risk | Immediate attention, strategic intervention |
| < 8 | Critical | Qualify out or escalate to leadership |

---

## Average Stage Duration Benchmarks

Adjust these based on your actual historical data:

| Stage | SMB (days) | Mid-Market (days) | Enterprise (days) |
|---|---|---|---|
| Prospecting → Qualified | 3 | 5 | 7 |
| Qualified → Discovery | 5 | 7 | 14 |
| Discovery → Demo | 5 | 10 | 14 |
| Demo → Proposal | 7 | 14 | 21 |
| Proposal → Negotiation | 5 | 14 | 21 |
| Negotiation → Close | 3 | 10 | 21 |
| **Total avg cycle** | **28** | **60** | **98** |

---

## At-Risk Flag Triggers

Automatically flag a deal if ANY of the following are true:

| Flag | Condition | Severity |
|---|---|---|
| Ghost | No activity in 14+ days | High |
| Stale close date | Close date passed without update | High |
| Stalled | In same stage for 2× avg duration | High |
| Single-threaded | Only one contact associated | Medium |
| No next step | No task or next step logged | Medium |
| Shrinking deal | Amount decreased > 20% | Medium |
| Missing EB | No economic buyer identified in deal > 30 days | Medium |
| Inactive champion | Champion hasn't responded in 10+ days | High |

---

## Pipeline Coverage Targets

| Quota Coverage | Interpretation | Action |
|---|---|---|
| > 4× quota | Overpipelined | Focus on qualification, remove unlikely deals |
| 3–4× quota | Healthy | Normal execution |
| 2–3× quota | Caution | Accelerate prospecting |
| < 2× quota | Danger | Urgent pipeline generation needed |

---

## Forecast Categories

| Category | Definition | Typical Close Probability |
|---|---|---|
| Commit | Rep is confident — deal will close this period | 80–100% |
| Best Case | Deal could close if everything goes right | 50–79% |
| Pipeline | In play but too early to forecast | 20–49% |
| Omitted | Not included in forecast | < 20% |

---

## Coaching Action Templates

Use these for the coaching section of pipeline reports:

**Stalled deal:**
> "Deal [X] has been in [stage] for [N] days (avg: [Y] days). Recommend: book a stakeholder call this week to re-establish timeline and surface blockers."

**Single-threaded:**
> "Deal [X] has only one contact ([name]). If they go dark, the deal dies. Recommend: ask champion to introduce economic buyer before [date]."

**No next step:**
> "Deal [X] has no next step logged. This is the #1 predictor of deal loss. Recommend: rep to re-engage today with a specific ask."

**Stale close date:**
> "Deal [X] has a close date of [date] that has passed. Update to reflect reality or mark at-risk. Pipeline hygiene affects forecast accuracy."

**Ghost:**
> "Deal [X] has had no activity in [N] days. Either re-engage with a new angle or move to closed-lost to clean the pipeline."
