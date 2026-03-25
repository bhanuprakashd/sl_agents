"""Sales Agent Team — root_agent export for ADK web discovery."""
import os, sys
from pathlib import Path

# Ensure aass_agents/ is on the path so sub-packages resolve correctly
_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

# Load .env so NVIDIA/model keys are available when ADK web imports this module
from dotenv import load_dotenv
load_dotenv(_HERE / ".env")

from agents.company_orchestrator_agent import company_orchestrator

root_agent = company_orchestrator
