from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

import httpx


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(override=False)


class MetadataClient(Protocol):
    def list_tools(self) -> list[Any]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


class CollateAIClient:
    def __init__(self, sdk_client: Any, config: Any | None = None):
        self._sdk_client = sdk_client
        self._config = config

    @classmethod
    def from_env(cls) -> "CollateAIClient":
        load_dotenv_if_available()
        try:
            from ai_sdk import AISdk, AISdkConfig
        except ImportError as exc:
            raise RuntimeError(
                "The Collate AI SDK is not installed. Install dependencies with: uv sync"
            ) from exc

        config = AISdkConfig.from_env()
        return cls(AISdk.from_config(config), config)

    def list_tools(self) -> list[Any]:
        if self._config is not None:
            result = self._make_jsonrpc_request("tools/list")
            return result.get("tools", [])
        return self._sdk_client.mcp.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._config is not None:
            return self._call_tool_sse(name, arguments)
        return self._sdk_client.mcp.call_tool(self._to_mcp_tool(name), arguments)

    @staticmethod
    def _to_mcp_tool(name: str) -> Any:
        try:
            from ai_sdk.mcp.models import MCPTool
        except ImportError:
            return name

        try:
            return MCPTool(name)
        except ValueError as exc:
            raise ValueError(f"Unsupported MCP tool: {name}") from exc

    def _call_tool_sse(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # Validate against the SDK's known enum while using an SSE-aware transport.
        tool = self._to_mcp_tool(name)
        result = self._make_jsonrpc_request(
            "tools/call",
            {"name": tool.value, "arguments": arguments},
        )
        if result.get("isError"):
            text = _first_text_content(result)
            raise RuntimeError(text or f"Tool execution failed: {name}")

        text = _first_text_content(result)
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        return data if isinstance(data, dict) else {"data": data}

    def _make_jsonrpc_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())[:8]
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        assert self._config is not None
        response = httpx.post(
            f"{self._config.host.rstrip('/')}/mcp",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Accept": "application/json, text/event-stream",
            },
            timeout=self._config.timeout,
            verify=self._config.verify_ssl,
        )
        response.raise_for_status()
        body = _parse_mcp_response(response)
        if "error" in body:
            error = body["error"]
            if isinstance(error, dict):
                raise RuntimeError(error.get("message") or str(error))
            raise RuntimeError(str(error))
        result = body.get("result", {})
        return result if isinstance(result, dict) else {"data": result}


def _parse_mcp_response(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    data_lines = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            value = line.removeprefix("data:").strip()
            if value and value != "[DONE]":
                data_lines.append(value)
    if not data_lines:
        return {}
    parsed = json.loads(data_lines[-1])
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _first_text_content(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            return str(first.get("text", ""))
    return ""
