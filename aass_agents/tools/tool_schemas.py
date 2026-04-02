"""
Tool Schemas — Pydantic input validation for ADK tool functions.

Borrowed from open-multi-agent's Zod-first pattern, adapted to Pydantic.
Validates tool inputs BEFORE execution, catching bad data early.

Usage:
    from tools.tool_schemas import validate_tool_input, BuildPhaseInput

    # In a tool function:
    def log_build_phase(product_id: str, phase: str, status: str, ...) -> str:
        # Validate inputs
        validated = validate_tool_input(BuildPhaseInput, {
            "product_id": product_id,
            "phase": phase,
            "status": status,
        })
        if validated.error:
            return validated.error
        # Use validated.data.product_id, etc.

    # Or as a decorator:
    @validated(BuildPhaseInput)
    def log_build_phase(data: BuildPhaseInput) -> str:
        ...
"""
import functools
import json
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator


T = TypeVar("T", bound=BaseModel)


# ── Validation Result ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidationResult(Generic[T]):
    """Result of input validation."""
    data: Optional[T]
    error: Optional[str]
    valid: bool


def validate_tool_input(schema: type[T], data: dict) -> ValidationResult[T]:
    """
    Validate a dict against a Pydantic schema.

    Returns ValidationResult with either validated data or error message.
    Never raises — always returns a result.
    """
    try:
        validated = schema.model_validate(data)
        return ValidationResult(data=validated, error=None, valid=True)
    except Exception as exc:
        error_msg = f"Input validation failed: {exc}"
        return ValidationResult(data=None, error=error_msg, valid=False)


def validated(schema: type[T]):
    """
    Decorator that validates tool inputs against a Pydantic schema.
    Returns JSON error string if validation fails.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(**kwargs) -> str:
            result = validate_tool_input(schema, kwargs)
            if not result.valid:
                return json.dumps({"error": result.error, "valid": False})
            return func(**kwargs)
        return wrapper
    return decorator


# ── Common Schemas ───────────────────────────────────────────────────────────

class BuildPhaseInput(BaseModel):
    """Input for log_build_phase tool."""
    product_id: str = Field(min_length=1, description="UUID of the product being built")
    phase: str = Field(
        min_length=1,
        description="Phase name (scaffold, features, polish, qa_test, fix_1, etc.)",
    )
    status: str = Field(description="Phase status")
    message: str = Field(default="", description="Human-readable status message")
    output_preview: str = Field(default="", max_length=2000, description="Output preview")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"starting", "running", "completed", "failed", "skipped"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v


class MessageInput(BaseModel):
    """Input for send_agent_message tool."""
    to_agent: str = Field(min_length=1, description="Recipient agent name")
    msg_type: str = Field(description="Message type")
    payload: str = Field(min_length=1, description="Message content")

    @field_validator("msg_type")
    @classmethod
    def validate_msg_type(cls, v: str) -> str:
        allowed = {"question", "answer", "notify", "data"}
        if v not in allowed:
            raise ValueError(f"msg_type must be one of {allowed}, got '{v}'")
        return v


class PipelineInput(BaseModel):
    """Input for run_parallel_pipeline tool."""
    pipeline_name: str = Field(min_length=1, description="Pipeline name")
    context_json: str = Field(default="{}", description="JSON context for prompt substitution")
    strategy: str = Field(default="dependency_first", description="Scheduling strategy")

    @field_validator("context_json")
    @classmethod
    def validate_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("context_json must be valid JSON")
        return v

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"dependency_first", "round_robin", "least_busy", "capability_match"}
        if v not in allowed:
            raise ValueError(f"strategy must be one of {allowed}, got '{v}'")
        return v


class MemoryInput(BaseModel):
    """Input for save_deal_context / save_product_state tools."""
    entity_id: str = Field(min_length=1, description="Entity identifier")
    data: str = Field(min_length=1, description="Data to save (JSON string)")

    @field_validator("data")
    @classmethod
    def validate_data_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("data must be valid JSON")
        return v


class ResearchInput(BaseModel):
    """Input for deep_research / search_company_web tools."""
    query: str = Field(min_length=2, max_length=2000, description="Research query")
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum results")


class ToolDiscoveryInput(BaseModel):
    """Input for discover_tools tool."""
    capability: str = Field(min_length=1, description="Capability to search for")
    department: str = Field(default="", description="Optional department filter")


class FeedbackInput(BaseModel):
    """Input for feedback tools."""
    product_id: str = Field(min_length=1, description="Product UUID")
    feedback: str = Field(default="", description="Feedback text")
    rating: int = Field(default=0, ge=0, le=10, description="Rating 0-10")


# ── Schema Registry ──────────────────────────────────────────────────────────

TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "log_build_phase": BuildPhaseInput,
    "send_agent_message": MessageInput,
    "run_parallel_pipeline": PipelineInput,
    "discover_tools": ToolDiscoveryInput,
}


def get_schema(tool_name: str) -> Optional[type[BaseModel]]:
    """Get the validation schema for a tool, or None if unregistered."""
    return TOOL_SCHEMAS.get(tool_name)
