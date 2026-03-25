"""
Engineering tools — pipeline spec registry and integration log for Engineering agents.
Session-scoped: stored in module-level dicts. Survives within a process; cleared on restart.
"""
from datetime import datetime, timezone

# Module-level session stores (reset on process restart)
_PIPELINE_REGISTRY: dict[str, dict] = {}
_INTEGRATION_REGISTRY: list[dict] = []


def create_pipeline_spec(
    name: str,
    stages: list[str],
    inputs: list[str],
    outputs: list[str],
) -> dict:
    """
    Define or update a pipeline specification and store it in the session registry.

    Args:
        name: Unique pipeline identifier (e.g. 'etl-raw-to-silver')
        stages: Ordered list of stage names (e.g. ['ingest', 'validate', 'transform'])
        inputs: List of input data sources or endpoints
        outputs: List of output destinations or endpoints

    Returns:
        dict with name, stages, inputs, outputs, status='defined', created_at
    """
    spec = {
        "name": name,
        "stages": list(stages),
        "inputs": list(inputs),
        "outputs": list(outputs),
        "status": "defined",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _PIPELINE_REGISTRY[name] = spec
    return spec


def get_pipeline_status(pipeline_name: str) -> dict:
    """
    Retrieve the current status snapshot for a named pipeline.

    Args:
        pipeline_name: The pipeline identifier used when calling create_pipeline_spec

    Returns:
        dict with found=True and pipeline fields, or found=False if not registered
    """
    spec = _PIPELINE_REGISTRY.get(pipeline_name)
    if spec is None:
        return {"found": False, "pipeline_name": pipeline_name}
    return {"found": True, **spec}


def log_integration(
    system_a: str,
    system_b: str,
    protocol: str,
    status: str,
) -> dict:
    """
    Record an integration link between two systems in the session registry.

    Args:
        system_a: Source system name
        system_b: Target system name
        protocol: Integration protocol (e.g. 'REST', 'gRPC', 'Kafka', 'Arrow Flight')
        status: Current status ('connected', 'pending', 'failed', 'deprecated')

    Returns:
        dict with system_a, system_b, protocol, status, logged_at
    """
    entry = {
        "system_a": system_a,
        "system_b": system_b,
        "protocol": protocol,
        "status": status,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    _INTEGRATION_REGISTRY.append(entry)
    return entry
