# tests/test_engineering_tools.py
"""Unit tests for engineering_tools — in-memory pipeline/integration state functions."""
import pytest


def test_create_pipeline_spec_returns_dict():
    from tools.engineering_tools import create_pipeline_spec
    result = create_pipeline_spec(
        name="etl-raw-to-silver",
        stages=["ingest", "validate", "transform"],
        inputs=["s3://raw/events"],
        outputs=["postgres://silver.events"],
    )
    assert result["name"] == "etl-raw-to-silver"
    assert result["stages"] == ["ingest", "validate", "transform"]
    assert result["inputs"] == ["s3://raw/events"]
    assert result["outputs"] == ["postgres://silver.events"]
    assert result["status"] == "defined"
    assert "created_at" in result


def test_create_pipeline_spec_persists_to_registry():
    from tools.engineering_tools import create_pipeline_spec, get_pipeline_status
    create_pipeline_spec(
        name="ml-training-pipeline",
        stages=["feature-eng", "train", "eval"],
        inputs=["feature-store"],
        outputs=["model-registry"],
    )
    result = get_pipeline_status("ml-training-pipeline")
    assert result["found"] is True
    assert result["name"] == "ml-training-pipeline"
    assert result["status"] == "defined"


def test_get_pipeline_status_not_found():
    from tools.engineering_tools import get_pipeline_status
    result = get_pipeline_status("nonexistent-pipeline")
    assert result["found"] is False


def test_log_integration_returns_entry():
    from tools.engineering_tools import log_integration
    result = log_integration(
        system_a="data-lake",
        system_b="feature-store",
        protocol="Apache Arrow Flight",
        status="connected",
    )
    assert result["system_a"] == "data-lake"
    assert result["system_b"] == "feature-store"
    assert result["protocol"] == "Apache Arrow Flight"
    assert result["status"] == "connected"
    assert "logged_at" in result


def test_log_integration_accumulates_entries():
    from tools.engineering_tools import log_integration, _INTEGRATION_REGISTRY
    _INTEGRATION_REGISTRY.clear()
    log_integration("svc-a", "svc-b", "gRPC", "connected")
    log_integration("svc-b", "svc-c", "REST", "pending")
    assert len(_INTEGRATION_REGISTRY) == 2


def test_get_pipeline_status_after_second_create_updates():
    from tools.engineering_tools import create_pipeline_spec, get_pipeline_status, _PIPELINE_REGISTRY
    _PIPELINE_REGISTRY.clear()
    create_pipeline_spec("pipe-x", ["a"], ["in"], ["out"])
    create_pipeline_spec("pipe-x", ["a", "b"], ["in2"], ["out2"])
    result = get_pipeline_status("pipe-x")
    assert result["stages"] == ["a", "b"]
