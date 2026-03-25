# CRM Field Mapping Reference

## Salesforce Field Names

### Opportunity (Deal) Object

| Concept | Salesforce Field API Name | Type | Notes |
|---|---|---|---|
| Deal name | `Name` | Text | |
| Account | `AccountId` | Lookup | Link to Account |
| Stage | `StageName` | Picklist | See stage values below |
| Amount | `Amount` | Currency | |
| Close date | `CloseDate` | Date | |
| Probability | `Probability` | Percent | Auto-set by stage |
| Deal type | `Type` | Picklist | New / Renewal / Expansion |
| Next step | `NextStep` | Text | 255 char limit |
| Description | `Description` | Long text | Full notes |
| Owner | `OwnerId` | Lookup | Rep assigned |
| Last activity | `LastActivityDate` | Date | Auto-updated |
| Lead source | `LeadSource` | Picklist | |
| Forecast category | `ForecastCategoryName` | Picklist | |

### Default Stage Values (customize per org)
- `Prospecting`
- `Qualification`
- `Needs Analysis`
- `Value Proposition`
- `Id. Decision Makers`
- `Perception Analysis`
- `Proposal/Price Quote`
- `Negotiation/Review`
- `Closed Won`
- `Closed Lost`

### Activity (Task) Object

| Concept | Field API Name | Type |
|---|---|---|
| Subject | `Subject` | Text |
| Due date | `ActivityDate` | Date |
| Status | `Status` | Picklist (Not Started / In Progress / Completed) |
| Priority | `Priority` | Picklist (Normal / High) |
| Description | `Description` | Long text |
| Related to (deal) | `WhatId` | Lookup |
| Assigned to | `OwnerId` | Lookup |

### Call Log (Event or Task)

| Concept | Field | Notes |
|---|---|---|
| Call type | Task: `Subject` = "Call - [type]" | Convention |
| Call notes | Task: `Description` | Full structured notes |
| Call date | Task: `ActivityDate` | |
| Duration | Task: custom field `Call_Duration__c` | If configured |

---

## HubSpot Field Names

### Deal Object

| Concept | HubSpot Property Name | Type | Notes |
|---|---|---|---|
| Deal name | `dealname` | Text | |
| Pipeline | `pipeline` | Enumeration | |
| Stage | `dealstage` | Enumeration | See stage IDs |
| Amount | `amount` | Number | |
| Close date | `closedate` | Date | Unix timestamp |
| Deal type | `dealtype` | Enumeration | newbusiness / existingbusiness |
| Description | `description` | Text | |
| Owner | `hubspot_owner_id` | Enumeration | |
| Last activity | `notes_last_updated` | Date | Auto |
| Priority | `hs_priority` | Enumeration | low / medium / high |
| Forecast | `hs_forecast_category` | Enumeration | |

### Default Pipeline Stage IDs (default pipeline)
- `appointmentscheduled` — Appointment Scheduled
- `qualifiedtobuy` — Qualified to Buy
- `presentationscheduled` — Presentation Scheduled
- `decisionmakerboughtin` — Decision Maker Bought-In
- `contractsent` — Contract Sent
- `closedwon` — Closed Won
- `closedlost` — Closed Lost

### Note / Activity Object

| Concept | HubSpot Property | Notes |
|---|---|---|
| Note body | `hs_note_body` | HTML or plain text |
| Timestamp | `hs_timestamp` | Unix ms |
| Owner | `hubspot_owner_id` | |
| Association | Associate to deal via `associations` | Required |

### Task Object

| Concept | Property | Notes |
|---|---|---|
| Subject | `hs_task_subject` | |
| Body / notes | `hs_task_body` | |
| Due date | `hs_timestamp` | Unix ms |
| Status | `hs_task_status` | NOT_STARTED / IN_PROGRESS / COMPLETED |
| Priority | `hs_task_priority` | LOW / MEDIUM / HIGH |
| Type | `hs_task_type` | CALL / EMAIL / TODO |

---

## Stage Progression Map

Use this to validate that stage updates follow the correct sequence:

```
New → Qualified → Discovery → Demo → Proposal → Negotiation → Closed Won/Lost
```

Never skip more than one stage forward without flagging it.
Never move a deal backward without noting the reason.

---

## Data Quality Rules

| Field | Rule |
|---|---|
| Close date | Must be in the future (unless closing) |
| Amount | Must be > 0 for any active opportunity |
| Next step | Must include a verb and a date |
| Stage | Must match activity level (no proposal without demo done) |
| Last activity | If > 14 days ago, flag as at-risk |
| Owner | Must be assigned — no unowned deals |
