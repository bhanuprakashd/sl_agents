# aass_agents/tools/railway_tools.py
"""
Railway GraphQL API tools for creating projects and deploying.
Requires: RAILWAY_TOKEN env var
"""
import os
import httpx

_RAILWAY_API = "https://backboard.railway.app/graphql/v2"
_TIMEOUT = 60


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['RAILWAY_TOKEN']}"}


def _gql(query: str, variables: dict | None = None) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            _RAILWAY_API,
            headers=_headers(),
            json={"query": query, "variables": variables or {}},
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(f"Railway GraphQL error: {data['errors']}")
        return data["data"]


def create_project(name: str) -> dict:
    """Create a Railway project. Returns project id."""
    query = """
    mutation ProjectCreate($input: ProjectCreateInput!) {
      projectCreate(input: $input) { id name }
    }
    """
    return _gql(query, {"input": {"name": name}})["projectCreate"]


def add_env_var(project_id: str, service_id: str, key: str, value: str) -> dict:
    """Add an environment variable to a Railway service."""
    query = """
    mutation VariableUpsert($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    return _gql(query, {"input": {"projectId": project_id, "serviceId": service_id,
                                   "environmentId": None, "name": key, "value": value}})


def deploy_from_github(project_id: str, repo_full_name: str, branch: str = "main") -> dict:
    """Connect a GitHub repo and deploy. Returns service info."""
    query = """
    mutation ServiceCreate($input: ServiceCreateInput!) {
      serviceCreate(input: $input) { id name }
    }
    """
    return _gql(query, {"input": {
        "projectId": project_id,
        "source": {"repo": repo_full_name, "branch": branch},
    }})["serviceCreate"]


def get_service_url(project_id: str, service_id: str) -> str:
    """Return the public URL for a Railway service."""
    query = """
    query ServiceDomains($projectId: String!, $serviceId: String!) {
      service(id: $serviceId) {
        domains { serviceDomains { domain } }
      }
    }
    """
    data = _gql(query, {"projectId": project_id, "serviceId": service_id})
    domains = data["service"]["domains"]["serviceDomains"]
    if not domains:
        return ""
    return f"https://{domains[0]['domain']}"
