from __future__ import annotations

from typing import Any

from data_discovery.client import MetadataClient


WRITE_TOOLS = {
    "patch_entity",
    "create_lineage",
    "create_glossary",
    "create_glossary_term",
    "create_test_case",
    "create_metric",
}


def call_tool(client: MetadataClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name in WRITE_TOOLS:
        raise ValueError(f"Refusing to call write tool: {name}")
    raw = client.call_tool(name, arguments)
    return unwrap_tool_result(raw)


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
