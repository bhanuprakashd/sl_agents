"""Shared data models for the sales agent team."""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class DealStage(str, Enum):
    PROSPECTING = "Prospecting"
    QUALIFIED = "Qualified"
    DISCOVERY = "Discovery"
    DEMO = "Demo"
    PROPOSAL = "Proposal"
    NEGOTIATION = "Negotiation"
    CLOSED_WON = "Closed Won"
    CLOSED_LOST = "Closed Lost"


class CallType(str, Enum):
    DISCOVERY = "discovery"
    DEMO = "demo"
    FOLLOWUP = "followup"
    NEGOTIATION = "negotiation"
    CLOSE = "close"


class OutreachChannel(str, Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    PHONE = "phone"


class Stakeholder(BaseModel):
    name: str
    title: str
    role: str  # champion / economic_buyer / influencer / blocker
    email: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None


class PainPoint(BaseModel):
    description: str
    severity: int = Field(ge=1, le=5)
    quantified_impact: Optional[str] = None
    source: str = "discovery"  # discovery / research / inferred


class DealContext(BaseModel):
    """Shared deal state passed between all agents."""
    deal_id: Optional[str] = None
    prospect_name: str
    prospect_title: str
    company_name: str
    company_website: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    stage: DealStage = DealStage.PROSPECTING
    deal_value: Optional[float] = None
    close_date: Optional[str] = None
    stakeholders: List[Stakeholder] = []
    pain_points: List[PainPoint] = []
    icp_fit_score: Optional[int] = None  # 1-5
    last_activity: Optional[str] = None
    next_step: Optional[str] = None
    next_step_date: Optional[str] = None
    open_risks: List[str] = []
    call_notes: List[str] = []
    outreach_sent: bool = False
    proposal_sent: bool = False
    crm_updated: bool = False


class ProspectResearch(BaseModel):
    company_overview: str
    recent_news: List[str]
    tech_stack: List[str]
    pain_points: List[str]
    buying_signals: List[str]
    decision_makers: List[Stakeholder]
    icp_fit_score: int = Field(ge=1, le=5)
    recommended_angle: str


class OutreachMessage(BaseModel):
    channel: OutreachChannel
    subject: Optional[str] = None  # email only
    body: str
    variant_b: Optional[str] = None
    subject_alternatives: List[str] = []
    reasoning: str


class CallBrief(BaseModel):
    call_type: CallType
    snapshot: str
    objectives: List[str]
    suggested_agenda: List[str]
    discovery_questions: List[dict]  # {question, purpose}
    demo_talk_track: List[dict]  # {pain, feature, proof}
    likely_objections: List[dict]  # {objection, response}
    stakeholder_map: List[Stakeholder]
    suggested_next_step: str
    risks: List[str]


class ObjectionResponse(BaseModel):
    objection_type: str
    immediate_response: str
    clarifying_question: str
    reframe: str
    leave_behind: Optional[str] = None
    is_smokescreen: bool = False


class Proposal(BaseModel):
    format: str  # one-pager / standard / business-case
    executive_summary: str
    challenge_section: str
    solution_section: str
    roi_model: dict
    differentiators: List[str]
    investment_section: str
    next_steps: List[str]
    email_cover_note: str


class DealHealthScore(BaseModel):
    deal_id: str
    company_name: str
    total_score: int = Field(ge=0, le=25)
    activity_recency: int = Field(ge=1, le=5)
    stage_velocity: int = Field(ge=1, le=5)
    stakeholder_coverage: int = Field(ge=1, le=5)
    timeline_alignment: int = Field(ge=1, le=5)
    next_step_clarity: int = Field(ge=1, le=5)
    health_rating: str  # Healthy / Caution / At Risk / Critical
    flags: List[str]
    recommended_actions: List[str]


class PipelineReport(BaseModel):
    period: str
    total_pipeline: float
    coverage_ratio: float
    weighted_forecast: float
    commit_forecast: float
    gap_to_quota: float
    commit_deals: List[dict]
    at_risk_deals: List[DealHealthScore]
    coaching_callouts: List[str]
    top_actions: List[str]
    data_quality_issues: List[str]
