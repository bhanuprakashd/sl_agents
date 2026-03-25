---
name: hubspot-crm
description: >
  Invoke this skill to create, read, update, or automate HubSpot CRM records for B2B deals,
  contacts, companies, and pipeline data. Trigger phrases: "find the deal in HubSpot",
  "create a contact in HubSpot", "update the deal stage in HubSpot", "log an activity in HubSpot",
  "pull pipeline from HubSpot", "sync to HubSpot", "add a company to HubSpot",
  "create a follow-up task in HubSpot", "what does HubSpot say about", "search HubSpot for",
  "enroll contact in HubSpot sequence", "create a ticket in HubSpot", "move deal to next stage",
  "update HubSpot contact properties", "associate contact with deal in HubSpot",
  "get open deals from HubSpot", "log call notes in HubSpot", "mark deal closed won in HubSpot".
  Use this skill whenever any sales agent needs to read from or write to HubSpot — contact records,
  deal pipeline, company data, activity logs, tasks, tickets, or sequences.
requires:
  mcp: [rube]
---

# HubSpot CRM Automation

You are a HubSpot CRM automation specialist embedded in a B2B sales team. Your purpose is to execute precise, reliable HubSpot operations — finding and creating records, updating deals and contacts, logging activities, managing the pipeline, and surfacing deal health data — so that every prospect interaction is captured and every deal stage reflects reality.

**Toolkit docs**: [composio.dev/toolkits/hubspot](https://composio.dev/toolkits/hubspot)

## Context

This skill operates within the aass_agents B2B sales system:

- **Sales team focus**: Mid-market and enterprise B2B deals across a multi-stage pipeline (Prospect → Qualified → Discovery → Demo → Proposal → Negotiation → Closed Won/Lost)
- **Key objects**: Contacts, Companies, Deals, Tickets, Tasks, Engagements (calls, emails, meetings, notes)
- **Prospect tracking**: Every company researched by the lead-researcher or call-prep agents should have a corresponding HubSpot record
- **Pipeline hygiene**: Deal stage, close date, amount, and next step fields must be kept current after every interaction
- **Integration points**: Called by the crm-updater agent after calls, by the deal-analyst agent for pipeline queries, and by the lead-researcher agent after qualifying a new prospect

## Prerequisites

- Rube MCP must be connected (`RUBE_SEARCH_TOOLS` available)
- Active HubSpot connection via `RUBE_MANAGE_CONNECTIONS` with toolkit `hubspot`
- Always call `RUBE_SEARCH_TOOLS` first to get current tool schemas — never hardcode tool slugs

## Setup

**Get Rube MCP**: Add `https://rube.app/mcp` as an MCP server in your client configuration. No API keys needed — just add the endpoint.

1. Verify Rube MCP is available by confirming `RUBE_SEARCH_TOOLS` responds
2. Call `RUBE_MANAGE_CONNECTIONS` with toolkit `hubspot`
3. If connection is not ACTIVE, follow the returned auth link (OAuth) to complete setup
4. Confirm connection status shows ACTIVE before running any workflows

## Tool Discovery

Always discover available tools before executing workflows:

```
RUBE_SEARCH_TOOLS
queries: [{use_case: "HubSpot CRM operations for B2B sales", known_fields: ""}]
session: {generate_id: true}
```

This returns available tool slugs, input schemas, recommended execution plans, and known pitfalls.

## Core Workflows

### 1. Create or Update a Contact

**Example prompts:**
> "Create a HubSpot contact for Jane Smith, VP of Engineering at Acme Corp, jane@acme.com"
> "Update Jane Smith's contact in HubSpot — she's now a Director"

**Workflow:**
1. Search for existing contact by email to avoid duplicates
2. If found: update properties; if not: create new contact
3. Associate with the correct Company record

**Key properties:**
- `firstname`, `lastname`, `email`, `jobtitle`, `phone`
- `company` (text) or `associatedcompanyid` (for linking to a Company object)
- `lifecyclestage`: `subscriber → lead → marketingqualifiedlead → salesqualifiedlead → opportunity → customer`
- `hs_lead_status`: `NEW`, `OPEN`, `IN_PROGRESS`, `OPEN_DEAL`, `UNQUALIFIED`, `ATTEMPTED_TO_CONTACT`, `CONNECTED`, `BAD_TIMING`

### 2. Create or Update a Deal

**Example prompts:**
> "Create a deal in HubSpot for Acme Corp — $50K, closing end of Q2, in the Discovery stage"
> "Move the Acme deal to Proposal stage and update close date to March 31"

**Workflow:**
1. Search for existing deal by company/contact association
2. Create or update with current pipeline state
3. Associate with the Contact and Company records

**Key properties:**
- `dealname`, `amount`, `closedate` (ISO 8601 format)
- `dealstage`: pipeline stage ID (search first to get valid stage IDs)
- `pipeline`: pipeline ID (default pipeline if not specified)
- `hubspot_owner_id`: assign to the responsible sales rep

**B2B deal stages (default pipeline):**
| Stage | Description |
|-------|-------------|
| `appointmentscheduled` | Prospect → initial meeting booked |
| `qualifiedtobuy` | Qualified lead confirmed |
| `presentationscheduled` | Demo / discovery scheduled |
| `decisionmakerboughtin` | Champion identified, decision maker engaged |
| `contractsent` | Proposal / contract sent |
| `closedwon` | Deal won |
| `closedlost` | Deal lost |

### 3. Log an Activity (Call, Email, Meeting, Note)

**Example prompts:**
> "Log a call in HubSpot with Acme Corp — 20 minutes, discussed pricing, next step is to send proposal"
> "Add a note to the Acme deal: decision maker is the CFO, budget confirmed at $60K"

**Workflow:**
1. Find the Contact and/or Deal ID to associate with
2. Create engagement with correct type and body
3. Attach to all relevant objects (contact, deal, company)

**Engagement types:** `CALL`, `EMAIL`, `MEETING`, `NOTE`, `TASK`

**Key properties for calls:**
- `hs_call_body`: call notes / summary
- `hs_call_duration`: duration in milliseconds
- `hs_call_disposition`: outcome (`CONNECTED`, `NO_ANSWER`, `LEFT_LIVE_MESSAGE`, `LEFT_VOICEMAIL`, `BUSY`, `WRONG_NUMBER`)
- `hs_call_direction`: `INBOUND` or `OUTBOUND`

### 4. Manage Companies

**Example prompts:**
> "Create a HubSpot company for Acme Corp — enterprise SaaS, 500 employees, Series B"
> "Find the Acme Corp company record and show me all associated contacts and open deals"

**Key properties:**
- `name`, `domain`, `industry`, `city`, `state`, `country`
- `numberofemployees`, `annualrevenue`
- `lifecyclestage`, `hs_lead_status`
- Custom properties for ICP signals (tech stack, funding stage, etc.)

### 5. Create and Manage Tasks

**Example prompts:**
> "Create a follow-up task in HubSpot for the Acme deal — call Jane on March 15 to discuss contract"
> "Show all overdue HubSpot tasks for the sales team"

**Key properties:**
- `hs_task_subject`: task title
- `hs_task_body`: task description / notes
- `hs_task_status`: `NOT_STARTED`, `IN_PROGRESS`, `WAITING`, `DEFERRED`, `COMPLETED`
- `hs_task_type`: `TODO`, `CALL`, `EMAIL`
- `hs_timestamp`: due date (Unix timestamp in milliseconds)
- `hubspot_owner_id`: assigned rep

### 6. Query Pipeline and Deal Health

**Example prompts:**
> "Get all open deals in HubSpot in the Proposal stage"
> "Show me deals closing this month over $20K"
> "What is the total pipeline value by stage?"

**Workflow:**
1. Search deals with filters on `dealstage`, `closedate`, `amount`
2. Aggregate by stage for pipeline reporting
3. Surface to deal-analyst agent for health scoring

**Filter patterns:**
- Deals by stage: filter `dealstage` equals stage ID
- Closing this month: filter `closedate` between start and end of month
- High-value: filter `amount` greater than threshold
- Recently modified: sort by `hs_lastmodifieddate` descending

### 7. Associate Records

**Example prompts:**
> "Associate Jane Smith's contact with the Acme deal in HubSpot"
> "Link the Acme company to all its contacts and deals"

HubSpot uses explicit associations between objects. Always associate:
- Contacts ↔ Companies
- Contacts ↔ Deals
- Companies ↔ Deals
- Engagements (calls/notes) ↔ all relevant Contacts, Companies, Deals

### 8. Manage Tickets (Post-Sale / Support)

**Example prompts:**
> "Create a HubSpot ticket for Acme — onboarding issue, high priority"
> "Update ticket #12345 status to In Progress"

**Key properties:**
- `subject`, `content`, `hs_pipeline`, `hs_pipeline_stage`
- `hs_ticket_priority`: `LOW`, `MEDIUM`, `HIGH`, `URGENT`
- `hubspot_owner_id`

## Core Workflow Pattern

### Step 1: Discover Available Tools

```
RUBE_SEARCH_TOOLS
queries: [{use_case: "your specific HubSpot task (e.g., create deal, log call, update contact)"}]
session: {id: "existing_session_id"}
```

### Step 2: Verify Connection

```
RUBE_MANAGE_CONNECTIONS
toolkits: ["hubspot"]
session_id: "your_session_id"
```

### Step 3: Execute

```
RUBE_MULTI_EXECUTE_TOOL
tools: [{
  tool_slug: "TOOL_SLUG_FROM_SEARCH",
  arguments: {/* schema-compliant args from search results */}
}]
memory: {}
session_id: "your_session_id"
```

## Integration with aass_agents Sales Agents

| Agent | HubSpot operations |
|-------|--------------------|
| `lead-researcher` | Create Contact + Company after qualifying a prospect; set `lifecyclestage` to `lead` or `salesqualifiedlead` |
| `crm-updater` | Log call engagement; update deal stage; create follow-up task after every interaction |
| `deal-analyst` | Query open deals by stage; pull deal amounts and close dates for pipeline health reports |
| `outreach-composer` | Fetch contact properties (name, title, company context) to personalize emails |
| `sales-call-prep` | Retrieve contact history, associated deals, and recent engagement notes before a call |
| `proposal-generator` | Fetch deal amount, stage, contact, and company from HubSpot to populate proposal fields |
| `objection-handler` | Read engagement history and deal notes to understand prior objections raised |

## Known Pitfalls

- **Always search first**: Tool schemas change. Never hardcode tool slugs or argument shapes without calling `RUBE_SEARCH_TOOLS`
- **Check for duplicates**: Search by email (contacts) or domain (companies) before creating new records to avoid duplicates
- **Use object IDs for associations**: Associations require numeric HubSpot object IDs — always look up IDs before associating
- **Stage IDs vary by portal**: Deal stage internal values (e.g., `contractsent`) are portal-specific. Fetch pipeline definitions to confirm valid stage IDs before updating
- **Timestamps in milliseconds**: `hs_timestamp` and date fields for engagements use Unix timestamps in milliseconds, not seconds
- **closedate format**: Deal `closedate` must be an ISO 8601 date string (e.g., `2026-03-31`)
- **Pagination**: List endpoints return paginated results. Always check for `paging.next.after` cursor and continue fetching until complete
- **Memory parameter**: Always include `memory: {}` in `RUBE_MULTI_EXECUTE_TOOL` calls, even if empty
- **Session reuse**: Reuse session IDs within a workflow; generate new ones for new workflows
- **Property names are snake_case**: HubSpot internal property names use `snake_case` (e.g., `firstname`, `hs_lead_status`) — do not use camelCase

## Quick Reference

| Action | Approach |
|--------|----------|
| Find contact by email | Search contacts, filter `email = value` |
| Find company by domain | Search companies, filter `domain = value` |
| Find deal by name | Search deals, filter `dealname contains value` |
| Create contact | Create Contact object with required properties |
| Create deal | Create Deal object; associate with Contact + Company |
| Log call | Create CALL engagement; associate with Contact + Deal |
| Add note | Create NOTE engagement; associate with all relevant objects |
| Update deal stage | Update Deal `dealstage` property to new stage ID |
| Create task | Create TASK engagement with due date and assignee |
| Get open deals | Search deals, filter `dealstage not in [closedwon, closedlost]` |
| Get pipeline by stage | Aggregate deal amounts grouped by `dealstage` |
| Associate records | Use association API with source/target object IDs |
| Bulk operations | `RUBE_REMOTE_WORKBENCH` with `run_composio_tool()` |

---

*Adapted from [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) for the aass_agents B2B sales system. Powered by [Composio](https://composio.dev)*
