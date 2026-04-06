"""Knowledge Graph tools — build, query, and visualize knowledge graphs using Graphify.

Wraps the graphify CLI to provide agents with programmatic access to
knowledge graph construction, querying, and export capabilities.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _run_graphify(args: list[str], timeout: int = 120) -> str:
    """Run a graphify CLI command and return stdout."""
    try:
        result = subprocess.run(
            ["graphify", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        if result.returncode != 0:
            return f"[graphify error] {result.stderr.strip() or result.stdout.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "[graphify error] graphify CLI not found. Install with: pip install graphifyy"
    except subprocess.TimeoutExpired:
        return f"[graphify error] Command timed out after {timeout}s"


def build_knowledge_graph(path: str, mode: str = "default") -> str:
    """Build a knowledge graph from a directory of files (code, docs, papers, images).

    Args:
        path: Directory or file path to process.
        mode: 'default' for balanced extraction, 'deep' for aggressive inference.

    Returns:
        Summary of the built graph including entity and relationship counts.
    """
    args = [path]
    if mode == "deep":
        args.append("--mode")
        args.append("deep")
    return _run_graphify(args, timeout=300)


def update_knowledge_graph(path: str) -> str:
    """Incrementally update an existing knowledge graph with new or changed files.

    Args:
        path: Directory or file path to process and merge into existing graph.

    Returns:
        Summary of updates applied to the graph.
    """
    return _run_graphify([path, "--update"], timeout=300)


def query_knowledge_graph(question: str) -> str:
    """Query the knowledge graph with a natural language question.

    Args:
        question: Natural language question about relationships in the graph.

    Returns:
        Answer synthesized from the knowledge graph.
    """
    return _run_graphify(["query", question])


def find_graph_path(source: str, target: str) -> str:
    """Find the relationship path between two entities in the knowledge graph.

    Args:
        source: Starting entity name (e.g. 'DigestAuth', 'UserService').
        target: Target entity name (e.g. 'Response', 'Database').

    Returns:
        Path description showing how the entities are connected.
    """
    return _run_graphify(["path", source, target])


def explain_entity(entity: str) -> str:
    """Get a detailed explanation of an entity and its relationships in the graph.

    Args:
        entity: Entity name to explain (e.g. 'SwinTransformer', 'AuthMiddleware').

    Returns:
        Explanation of the entity including its connections and role.
    """
    return _run_graphify(["explain", entity])


def add_to_knowledge_graph(url: str) -> str:
    """Add content from a URL to the knowledge graph (papers, tweets, web pages).

    Args:
        url: URL to fetch and add (supports arxiv, twitter/x, and general web pages).

    Returns:
        Summary of entities and relationships extracted from the URL.
    """
    return _run_graphify(["add", url], timeout=180)


def export_knowledge_graph(format: str = "json") -> str:
    """Export the knowledge graph in a specified format.

    Args:
        format: Export format — 'json', 'graphml' (Gephi/yEd), 'svg', or 'neo4j' (Cypher queries).

    Returns:
        Exported graph data or path to the exported file.
    """
    flag = f"--{format}"
    return _run_graphify(["export", flag] if format != "json" else ["export"])
