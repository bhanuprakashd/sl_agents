"""CRM tools for Salesforce and HubSpot integration."""

import os
from google.adk.tools import tool
from typing import Optional
import httpx


def _get_sf_headers() -> dict:
    """Get Salesforce auth headers. In production, use OAuth2 flow."""
    token = os.getenv("SALESFORCE_ACCESS_TOKEN", "")
    instance = os.getenv("SALESFORCE_INSTANCE_URL", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "instance_url": instance,
    }


def _get_hs_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('HUBSPOT_API_KEY', '')}",
        "Content-Type": "application/json",
    }


# ── Salesforce Tools ──────────────────────────────────────────────────────────

@tool
def sf_find_opportunity(company_name: str) -> dict:
    """
    Find an opportunity in Salesforce by company name.

    Args:
        company_name: Account/company name to search for

    Returns:
        dict with opportunity details or empty if not found
    """
    headers = _get_sf_headers()
    instance_url = headers.pop("instance_url")
    query = f"SELECT Id, Name, StageName, Amount, CloseDate, NextStep, Description, LastActivityDate FROM Opportunity WHERE Account.Name LIKE '%{company_name}%' AND IsClosed = false ORDER BY LastModifiedDate DESC LIMIT 5"

    response = httpx.get(
        f"{instance_url}/services/data/v59.0/query?q={query}",
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    records = data.get("records", [])

    # Verification: flag if returned records don't match the searched company name
    name_lower = company_name.lower()
    for rec in records:
        account_name = (rec.get("Account", {}) or {}).get("Name", "")
        rec["_match_confidence"] = "confirmed" if name_lower in account_name.lower() else "partial"

    unconfirmed = [r for r in records if r.get("_match_confidence") == "partial"]
    return {
        "records": records,
        "total": data.get("totalSize", 0),
        "verification": {
            "searched_for": company_name,
            "warning": f"{len(unconfirmed)} record(s) may not match — confirm before updating" if unconfirmed else None,
        },
    }


@tool
def sf_update_opportunity(
    opportunity_id: str,
    stage: Optional[str] = None,
    amount: Optional[float] = None,
    close_date: Optional[str] = None,
    next_step: Optional[str] = None,
) -> dict:
    """
    Update an opportunity record in Salesforce.

    Args:
        opportunity_id: Salesforce Opportunity ID (18-char)
        stage: New stage name (e.g., 'Demo', 'Proposal/Price Quote')
        amount: Deal amount in dollars
        close_date: Expected close date in YYYY-MM-DD format
        next_step: Next step text (255 char max)

    Returns:
        dict confirming what was updated
    """
    headers = _get_sf_headers()
    instance_url = headers.pop("instance_url")

    payload = {}
    if stage:
        payload["StageName"] = stage
    if amount is not None:
        payload["Amount"] = amount
    if close_date:
        payload["CloseDate"] = close_date
    if next_step:
        payload["NextStep"] = next_step[:255]

    if not payload:
        return {"error": "No fields to update provided"}

    response = httpx.patch(
        f"{instance_url}/services/data/v59.0/sobjects/Opportunity/{opportunity_id}",
        headers=headers,
        json=payload,
        timeout=15,
    )
    if response.status_code == 204:
        return {"success": True, "updated_fields": list(payload.keys()), "opportunity_id": opportunity_id}
    response.raise_for_status()
    return response.json()


@tool
def sf_log_call(
    opportunity_id: str,
    subject: str,
    notes: str,
    call_date: str,
) -> dict:
    """
    Log a call activity on a Salesforce opportunity.

    Args:
        opportunity_id: Related Opportunity ID
        subject: Call subject line (e.g., 'Discovery Call - Acme Corp')
        notes: Structured call notes
        call_date: Date of call in YYYY-MM-DD format

    Returns:
        dict with created Task ID
    """
    headers = _get_sf_headers()
    instance_url = headers.pop("instance_url")

    payload = {
        "Subject": subject[:255],
        "Description": notes,
        "ActivityDate": call_date,
        "Status": "Completed",
        "WhatId": opportunity_id,
        "Type": "Call",
    }

    response = httpx.post(
        f"{instance_url}/services/data/v59.0/sobjects/Task",
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@tool
def sf_create_task(
    opportunity_id: str,
    subject: str,
    due_date: str,
    notes: Optional[str] = None,
    priority: str = "Normal",
) -> dict:
    """
    Create a follow-up task on a Salesforce opportunity.

    Args:
        opportunity_id: Related Opportunity ID
        subject: Task description
        due_date: Due date in YYYY-MM-DD format
        notes: Optional additional notes
        priority: 'Normal' or 'High'

    Returns:
        dict with created Task ID
    """
    headers = _get_sf_headers()
    instance_url = headers.pop("instance_url")

    payload = {
        "Subject": subject[:255],
        "ActivityDate": due_date,
        "Status": "Not Started",
        "Priority": priority,
        "WhatId": opportunity_id,
    }
    if notes:
        payload["Description"] = notes

    response = httpx.post(
        f"{instance_url}/services/data/v59.0/sobjects/Task",
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@tool
def sf_get_pipeline(owner_id: Optional[str] = None, fiscal_quarter: Optional[str] = None) -> dict:
    """
    Fetch all open pipeline opportunities from Salesforce.

    Args:
        owner_id: Filter by rep's Salesforce User ID (optional)
        fiscal_quarter: Filter by fiscal quarter e.g. '2026Q1' (optional)

    Returns:
        dict with list of open opportunities and metrics
    """
    from urllib.parse import quote

    headers = _get_sf_headers()
    instance_url = headers.pop("instance_url")

    where_clauses = ["IsClosed = false"]
    if owner_id:
        where_clauses.append(f"OwnerId = '{owner_id}'")

    query = (
        "SELECT Id, Name, Account.Name, StageName, Amount, Probability, "
        "CloseDate, LastActivityDate, NextStep, OwnerId, CreatedDate "
        "FROM Opportunity "
        f"WHERE {' AND '.join(where_clauses)} "
        "ORDER BY Amount DESC LIMIT 200"
    )

    response = httpx.get(
        f"{instance_url}/services/data/v59.0/query?q={quote(query)}",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


# ── HubSpot Tools ─────────────────────────────────────────────────────────────

@tool
def hs_find_deal(company_name: str) -> dict:
    """
    Find a HubSpot deal by company name.

    Args:
        company_name: Company name to search for

    Returns:
        dict with deal properties
    """
    headers = _get_hs_headers()
    response = httpx.post(
        "https://api.hubapi.com/crm/v3/objects/deals/search",
        headers=headers,
        json={
            "filterGroups": [{
                "filters": [{
                    "propertyName": "associations.company",
                    "operator": "HAS_PROPERTY",
                }]
            }],
            "properties": ["dealname", "dealstage", "amount", "closedate", "hs_next_step", "notes_last_updated"],
            "query": company_name,
            "limit": 5,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@tool
def hs_log_note(deal_id: str, note_body: str) -> dict:
    """
    Log a note on a HubSpot deal.

    Args:
        deal_id: HubSpot Deal ID
        note_body: Note content (HTML or plain text)

    Returns:
        dict with created note ID
    """
    import time
    headers = _get_hs_headers()
    payload = {
        "properties": {
            "hs_note_body": note_body,
            "hs_timestamp": str(int(time.time() * 1000)),
        },
        "associations": [{
            "to": {"id": deal_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}],
        }],
    }

    response = httpx.post(
        "https://api.hubapi.com/crm/v3/objects/notes",
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@tool
def hs_update_deal(
    deal_id: str,
    stage: Optional[str] = None,
    amount: Optional[float] = None,
    close_date: Optional[str] = None,
    next_step: Optional[str] = None,
) -> dict:
    """
    Update a HubSpot deal's properties.

    Args:
        deal_id: HubSpot Deal ID
        stage: New pipeline stage (HubSpot internal stage ID or label)
        amount: Deal value in dollars
        close_date: Expected close date in YYYY-MM-DD format
        next_step: Next step description

    Returns:
        dict with updated deal properties
    """
    headers = _get_hs_headers()
    properties: dict = {}
    if stage:
        properties["dealstage"] = stage
    if amount is not None:
        properties["amount"] = str(amount)
    if close_date:
        properties["closedate"] = close_date
    if next_step:
        properties["hs_next_step"] = next_step

    if not properties:
        return {"error": "No fields to update provided"}

    response = httpx.patch(
        f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}",
        headers=headers,
        json={"properties": properties},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@tool
def hs_create_task(
    deal_id: str,
    subject: str,
    due_date: str,
    notes: Optional[str] = None,
    priority: str = "MEDIUM",
) -> dict:
    """
    Create a follow-up task associated with a HubSpot deal.

    Args:
        deal_id: HubSpot Deal ID to associate the task with
        subject: Task title/description
        due_date: Due date in YYYY-MM-DD format
        notes: Optional task body/notes
        priority: 'LOW', 'MEDIUM', or 'HIGH'

    Returns:
        dict with created task ID
    """
    import time
    from datetime import datetime

    headers = _get_hs_headers()

    # HubSpot tasks use millisecond epoch timestamps for due date
    due_ts = int(datetime.strptime(due_date, "%Y-%m-%d").timestamp() * 1000)

    properties: dict = {
        "hs_task_subject": subject,
        "hs_task_status": "NOT_STARTED",
        "hs_task_priority": priority.upper(),
        "hs_timestamp": str(int(time.time() * 1000)),
        "hs_task_due_date": str(due_ts),
    }
    if notes:
        properties["hs_task_body"] = notes

    payload = {
        "properties": properties,
        "associations": [{
            "to": {"id": deal_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 216}],
        }],
    }

    response = httpx.post(
        "https://api.hubapi.com/crm/v3/objects/tasks",
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
