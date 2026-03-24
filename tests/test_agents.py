"""
Smoke tests for the Sales Agent Team.
Tests triggering, routing, and basic functional outputs.
"""

import pytest
import asyncio
import os
os.environ.setdefault("MODEL_ID", "gemini-2.0-flash")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from agents.sales_orchestrator_agent import sales_orchestrator


APP_NAME = "sales-agent-test"
USER_ID = "test-user"


async def run_query(session_service, session_id: str, query: str) -> str:
    """Run a single query and return the final response text."""
    runner = Runner(
        agent=sales_orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )
    content = Content(role="user", parts=[Part(text=query)])
    response_text = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            response_text = event.content.parts[0].text
    return response_text


@pytest.fixture
async def session():
    svc = InMemorySessionService()
    sid = "test-session-001"
    await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sid)
    return svc, sid


# ── Routing Tests ──────────────────────────────────────────────────────────────

class TestRouting:
    """Verify orchestrator routes to correct sub-agent."""

    @pytest.mark.asyncio
    async def test_routes_research_request(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Research Acme Corp for me")
        assert any(kw in response.lower() for kw in ["company", "research", "profile", "acme"])

    @pytest.mark.asyncio
    async def test_routes_outreach_request(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Write a cold email to the VP of Sales at Stripe")
        assert any(kw in response.lower() for kw in ["subject", "email", "stripe", "cta"])

    @pytest.mark.asyncio
    async def test_routes_call_prep_request(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Prep me for my discovery call with Notion tomorrow")
        assert any(kw in response.lower() for kw in ["call", "discovery", "question", "agenda"])

    @pytest.mark.asyncio
    async def test_routes_objection(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "The prospect said it's too expensive")
        assert any(kw in response.lower() for kw in ["price", "roi", "value", "acknowledge", "clarify"])

    @pytest.mark.asyncio
    async def test_routes_proposal_request(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Write a proposal for Airbnb — mid-market deal")
        assert any(kw in response.lower() for kw in ["proposal", "executive", "challenge", "investment"])

    @pytest.mark.asyncio
    async def test_routes_pipeline_review(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Give me a pipeline review for this quarter")
        assert any(kw in response.lower() for kw in ["pipeline", "forecast", "at-risk", "coverage"])


# ── Functional Tests ───────────────────────────────────────────────────────────

class TestOutreachComposer:
    @pytest.mark.asyncio
    async def test_cold_email_has_subject(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Write a cold email to Sarah Chen, VP Sales at Figma")
        assert "subject" in response.lower()

    @pytest.mark.asyncio
    async def test_produces_variant_b(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Write outreach for John at HubSpot — cold email")
        assert "variant" in response.lower() or "option b" in response.lower() or "alternative" in response.lower()

    @pytest.mark.asyncio
    async def test_no_hope_this_finds_you_well(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Write cold email to CMO at Salesforce")
        assert "hope this email finds you well" not in response.lower()


class TestObjectionHandler:
    @pytest.mark.asyncio
    async def test_price_objection_has_four_parts(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "They said our price is too high compared to competitors")
        # Should have: immediate response, clarifying question, reframe, leave-behind
        assert len(response) > 200  # substantive response

    @pytest.mark.asyncio
    async def test_timing_objection(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "Prospect said come back next quarter")
        assert any(kw in response.lower() for kw in ["timing", "quarter", "urgency", "changes"])

    @pytest.mark.asyncio
    async def test_competitor_objection(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "They said they're happy with Salesforce")
        assert any(kw in response.lower() for kw in ["salesforce", "work around", "criteria", "compare"])


# ── Non-Triggering Tests ───────────────────────────────────────────────────────

class TestNonTriggering:
    @pytest.mark.asyncio
    async def test_does_not_trigger_on_unrelated(self, session):
        svc, sid = session
        response = await run_query(svc, sid, "What's the weather in San Francisco?")
        # Should respond helpfully but not run a sales workflow
        assert "deal card" not in response.lower()
        assert "pipeline" not in response.lower()
