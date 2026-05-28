from __future__ import annotations

from typing import Any

from data_discovery.client import MetadataClient
from data_discovery.models import ToolPlan


READ_TOOLS = {"semantic_search", "search_metadata", "get_entity_details", "get_entity_lineage"}
WRITE_TOOLS = {
    "patch_entity",
    "create_lineage",
    "create_glossary",
    "create_glossary_term",
    "create_test_case",
    "create_metric",
}


def list_tool_names(client: MetadataClient) -> set[str]:
    try:
        tools = client.list_tools()
    except Exception:
        return set()

    names = set()
    for tool in tools:
        if isinstance(tool, str):
            names.add(tool)
        elif isinstance(tool, dict) and "name" in tool:
            names.add(str(tool["name"]))
        elif hasattr(tool, "name"):
            names.add(str(tool.name))
    return names


def call_planned_tool(client: MetadataClient, plan: ToolPlan) -> dict[str, Any]:
    return call_tool(client, plan.primary_tool, plan.arguments)


def call_tool(client: MetadataClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name in WRITE_TOOLS:
        raise ValueError(f"Refusing to call write tool: {name}")
    raw = client.call_tool(name, arguments)
    return unwrap_tool_result(raw)


def get_entity_details(client: MetadataClient, entity_type: str, fqn: str) -> dict[str, Any]:
    return call_tool(client, "get_entity_details", {"entityType": entity_type, "fqn": fqn})


def unwrap_tool_result(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "data"):
        data = raw.data
        if isinstance(data, dict):
            return data
        return {"data": data}
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {"data": raw}
