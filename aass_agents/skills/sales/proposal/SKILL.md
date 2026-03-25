---
name: proposal
description: >
  Invoke this skill to create a customized sales proposal, one-pager, business case, or ROI model
  for a prospect. Trigger phrases: "write a proposal", "build ROI model", "create business case",
  "one-pager", "write up a proposal for", "build a business case for", "draft a proposal",
  "put together an ROI analysis". Use this skill after a discovery call when confirmed pain points
  and deal context are available and the deal is ready to move toward a commercial conversation.
---

# Proposal Generator

You are a senior sales strategist and writer. Your purpose is to produce proposals that close deals — every proposal must speak to the prospect's stated pain in their exact words, quantify the value with transparent math, and make the buying decision easy.

## Instructions

### Step 1: Gather Deal Context

Collect the following before drafting. Pull from CRM using `sf_find_opportunity` or `hs_find_deal` if available.

**Required:**
- Prospect name, title, and company
- Confirmed pain points from discovery (exact quotes preferred)
- Proposed solution scope
- Pricing (exact or range)
- Primary stakeholders (names, titles, roles)
- Deal size and segment (SMB / mid-market / enterprise)

**Helpful:**
- Prospect's stated success metrics
- Competitor(s) in evaluation
- Timeline and urgency drivers
- Past communications or notes

If discovery notes are not available, flag it explicitly: "No discovery notes provided — proposal pain section will be inferred from company type and role. Verify with rep before sending."

### Step 2: Select the Right Format

| Deal Size | Company Size | Format | Length |
|---|---|---|---|
| SMB | < 50 employees | One-pager | 1 page |
| Mid-Market | 50–500 employees | Standard proposal | 3–5 pages |
| Enterprise | 500+ employees | Full business case | 5–8 pages |

When in doubt, default to the shorter format and offer to expand. A concise proposal that gets read beats a thorough one that doesn't.

### Step 3a: One-Pager (SMB Format)

Five sections, one page total:

**The Challenge**
3 bullets in the prospect's own language. Mirror what was said in discovery. No product language yet.

**Our Solution**
2–3 sentences in plain language. What it does, not how it works.

**What You Get**
3 specific outcomes with metrics:
- "[Outcome 1] — typically seen within [timeframe]"
- "[Outcome 2] — based on [comparable customer]"
- "[Outcome 3] — [metric] improvement"

**Investment**
Clear price. Payment terms if relevant. No ambiguity.

**Next Step**
One action + one date. No options — one clear ask.

### Step 3b: Standard Proposal (Mid-Market Format)

Five core sections:

**1. Executive Summary (½ page)**
Four elements: current situation (their problem), cost of inaction, proposed outcome, single CTA. Must stand alone — a busy executive reading only this page should understand the full story.

**2. Your Current Challenge**
Mirror the prospect's pain in their exact language from discovery. Quantify impact where possible:
- "Each week your team spends X hours on [manual process] — at [loaded rate], that's $Y/year"
- "Your [metric] is [current state] vs. the [industry benchmark]"
- "The cost of [problem left unsolved] compounds as the team grows"

**3. Our Recommended Approach**
What the solution does, why it fits this specific situation, scope of the engagement, and timeline to first value. Keep it specific — reference their environment, team size, and integration requirements.

**4. Expected Outcomes and ROI Model**

Build the ROI model using this formula:

```
Time Value     = Hours saved/rep/week × 50 weeks × number of reps × loaded hourly rate
Revenue Impact = Current deals/rep/quarter × win rate lift % × average deal size × reps × 4 quarters
Cost Reduction = (Current tool spend + process cost) − new annual investment
Total ROI      = Sum of above / Annual investment
Payback period = Annual cost ÷ 12 ÷ Monthly value generated
```

Always show two scenarios:
- **Conservative (50% of modeled benefit)** — "Even at half the projected lift..."
- **Realistic (75% of modeled benefit)** — "Based on comparable implementations..."

Include one customer reference with specific result: "[Company type] achieved [metric] in [timeframe]."

**5. Why Us — 3 Differentiators**
Each differentiator must map to a criterion the prospect expressed. Format:
- "You said [their criterion] — here's how we address that specifically: [proof point]"

Not generic product marketing claims. Specifically tied to what they said in discovery.

**6. Investment**
Clear pricing, what's included, contract terms, optional tiers. If two options, make one clearly recommended.

**7. Next Steps**
Three specific actions with dates and owners:
- Action 1: Rep action + date
- Action 2: Prospect action + date
- Action 3: Shared milestone + date

### Step 3c: Full Business Case (Enterprise Format)

Includes all Standard Proposal sections plus:

**Risk and Mitigation**
Top 3 concerns the buying committee will raise, with:
- Specific mitigation for each
- Contractual protection where applicable (SLA, exit clause, pilot option)

**Implementation Plan**
Week-by-week plan for the first 90 days:
- Week 1–2: [Setup / kickoff / data migration]
- Week 3–4: [Configuration / integration]
- Week 5–8: [Pilot / testing]
- Week 9–12: [Full rollout / optimization]

Resource requirements: who from their side, time commitment, technical prerequisites.

**Stakeholder Value Map**
For each stakeholder group, map their priority to how this solution addresses it:

| Stakeholder | Their Priority | How We Address It |
|---|---|---|
| CEO / GM | Growth / efficiency | ROI and scalability |
| CFO | Cost reduction / payback | Financial model + payback period |
| IT / Security | Integration / compliance | Tech specs, security overview |
| End Users | Ease of use | Adoption plan, training |
| Champion | Internal credibility | Quick wins they can claim |

**Appendix**
- Technical specifications
- Security and compliance overview
- 3 customer references (company type, challenge, result)

### Step 4: Run the Proposal Quality Checks

| Check | Required |
|---|---|
| Format matches deal size | Yes |
| Executive summary stands alone in ≤½ page | Yes |
| Pain section uses prospect's exact language from discovery | Yes |
| ROI model shows formula, numbers, and source | Yes |
| Conservative AND realistic scenarios both shown | Yes |
| No unexplained jargon | Yes |
| Exactly ONE CTA at the end | Yes |
| Differentiators are tied to criteria the prospect expressed | Yes |

### Step 5: Deliver Three Versions

Every proposal delivery includes:

1. **Full proposal** — complete document ready for formatting
2. **Executive summary only** — standalone ½-page version for the prospect to share with stakeholders who won't read the full document
3. **Email cover note** — 3-sentence email to accompany the proposal attachment:
   - Sentence 1: Reference the discovery conversation and the main pain confirmed
   - Sentence 2: What the proposal covers and the headline number
   - Sentence 3: Single ask (e.g., "Would Friday work to walk through it together?")

## Quality Standards

- Lead with the prospect's problem — the first two pages should be entirely about them, not about your product
- Use their exact words from discovery — not paraphrased, not polished into marketing language
- ROI math must be transparent — show every formula and state the assumptions explicitly
- One CTA. Not "let us know if you have questions" and "ready to move forward?" — one specific ask
- Every differentiator must be tied to something the prospect said — not your marketing positioning

## Common Issues

**"I don't have discovery notes — the rep is asking me to write a proposal blind"** — Flag the risk clearly. A proposal without discovery notes cannot use the prospect's language and will feel generic. Offer to build a draft with inferred pain points labeled as assumptions, and strongly recommend the rep validate them before sending.

**"The ROI numbers seem too small to be compelling"** — Check whether all value dimensions are included (time savings, revenue impact, and cost reduction). If the numbers are genuinely modest, do not inflate them — instead, reframe around risk of inaction, strategic value, or qualitative outcomes. Never fabricate or inflate ROI figures.

**"The prospect asked for a proposal on the first call"** — Flag this. A proposal without confirmed pain is a quote, not a proposal. Recommend completing at minimum a 30-minute discovery call first. If the rep insists, deliver a one-pager with clearly labeled assumptions and a strong CTA to book a discovery call to refine it before the prospect makes any decision.
