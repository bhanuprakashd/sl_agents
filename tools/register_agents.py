# sales-adk-agents/tools/register_agents.py
"""
ADK agent hierarchy definition.
Used by generate_orgchart.py to build the standalone HTML org chart.
"""

from dataclasses import dataclass, field


@dataclass
class AgentNode:
    name: str                       # ADK agent name (matches Agent(name=...) exactly)
    role: str                       # Visual role for org chart colouring
    title: str                      # Human-readable title
    capabilities: str               # One-liner for org chart card
    children: list["AgentNode"] = field(default_factory=list)


AGENT_TREE = AgentNode(
    name="company_orchestrator",
    role="ceo",
    title="Company Orchestrator",
    capabilities="Top-level GTM orchestrator — routes to Sales, Marketing, and Product teams",
    children=[
        AgentNode(
            name="marketing_orchestrator",
            role="cmo",
            title="Marketing Orchestrator",
            capabilities="Demand generation, campaigns, content, SEO, performance analytics",
            children=[
                AgentNode(
                    name="audience_builder",
                    role="researcher",
                    title="Audience Builder",
                    capabilities="Builds ICP audiences and Tier 1 MQL lists",
                ),
                AgentNode(
                    name="campaign_composer",
                    role="general",
                    title="Campaign Composer",
                    capabilities="Creates email, LinkedIn, and landing page campaigns",
                ),
                AgentNode(
                    name="content_strategist",
                    role="general",
                    title="Content Strategist",
                    capabilities="Content briefs, blog posts, SEO-aligned content plans",
                ),
                AgentNode(
                    name="seo_analyst",
                    role="researcher",
                    title="SEO Analyst",
                    capabilities="Keyword strategy, on-page SEO, search signal analysis",
                ),
                AgentNode(
                    name="campaign_analyst",
                    role="researcher",
                    title="Campaign Analyst",
                    capabilities="Campaign performance measurement and A/B test analysis",
                ),
                AgentNode(
                    name="brand_voice",
                    role="general",
                    title="Brand Voice Agent",
                    capabilities="Reviews copy for brand consistency before launch",
                ),
            ],
        ),
        AgentNode(
            name="sales_orchestrator",
            role="general",
            title="Sales Orchestrator",
            capabilities="Full revenue cycle — research, outreach, proposals, CRM, pipeline",
            children=[
                AgentNode(
                    name="lead_researcher",
                    role="researcher",
                    title="Lead Researcher",
                    capabilities="Researches prospects and builds structured company profiles",
                ),
                AgentNode(
                    name="outreach_composer",
                    role="general",
                    title="Outreach Composer",
                    capabilities="Writes personalised cold emails and LinkedIn messages",
                ),
                AgentNode(
                    name="sales_call_prep",
                    role="general",
                    title="Sales Call Prep",
                    capabilities="Generates call briefs and discovery question frameworks",
                ),
                AgentNode(
                    name="objection_handler",
                    role="general",
                    title="Objection Handler",
                    capabilities="Live deal support — counters objections with evidence",
                ),
                AgentNode(
                    name="proposal_generator",
                    role="general",
                    title="Proposal Generator",
                    capabilities="Writes tailored business cases and proposals",
                ),
                AgentNode(
                    name="crm_updater",
                    role="general",
                    title="CRM Updater",
                    capabilities="Logs calls, updates deal stages, creates follow-up tasks",
                ),
                AgentNode(
                    name="deal_analyst",
                    role="researcher",
                    title="Deal Analyst",
                    capabilities="Pipeline reviews, deal health scoring, and forecasting",
                ),
            ],
        ),
        AgentNode(
            name="product_orchestrator",
            role="cto",
            title="Product Orchestrator",
            capabilities="Autonomous product pipeline — requirement to live deployed SaaS",
            children=[
                AgentNode(
                    name="pm_agent",
                    role="pm",
                    title="PM Agent",
                    capabilities="Converts requirements into structured PRDs with market research",
                ),
                AgentNode(
                    name="architect_agent",
                    role="engineer",
                    title="Architect Agent",
                    capabilities="Picks tech stack deterministically and generates file tree",
                ),
                AgentNode(
                    name="devops_agent",
                    role="devops",
                    title="DevOps Agent",
                    capabilities="Provisions GitHub repo, Vercel project, Railway project",
                ),
                AgentNode(
                    name="db_agent",
                    role="engineer",
                    title="DB Agent",
                    capabilities="Generates SQL schema, provisions NeonDB or Supabase",
                ),
                AgentNode(
                    name="backend_builder_agent",
                    role="engineer",
                    title="Backend Builder",
                    capabilities="Generates FastAPI backend code and deploys to Railway",
                ),
                AgentNode(
                    name="frontend_builder_agent",
                    role="designer",
                    title="Frontend Builder",
                    capabilities="Generates Next.js + Tailwind UI and deploys to Vercel",
                ),
                AgentNode(
                    name="qa_agent",
                    role="qa",
                    title="QA Agent",
                    capabilities="Smoke tests the live deployment — root, health, auth",
                ),
            ],
        ),
    ],
)
