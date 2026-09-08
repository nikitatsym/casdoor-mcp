from __future__ import annotations

import asyncio
import json
from typing import Literal

import httpx
import pytest
from mcp.types import TextContent

from casdoor_mcp import server, tools
from casdoor_mcp.client import APIError


def _registered(name: str):
    fn = server.mcp._tool_manager._tools[name].fn

    def call(*args, **kwargs):
        result = fn(*args, **kwargs)
        return json.loads(result.text) if isinstance(result, TextContent) else result

    return call


def _raise(exc: Exception):
    raise exc


def test_registered_tools_return_compact_json_without_structured_content():
    for tool in server.mcp._tool_manager.list_tools():
        assert tool.fn_metadata.output_schema is None

    result = asyncio.run(server.mcp.call_tool("casdoor_read", {"operation": "NoSuchOp"}))

    assert result.structured_content is None
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, TextContent)
    assert "\n" not in content.text
    assert json.loads(content.text) == {
        "error": 'Unknown operation: NoSuchOp. Use operation="help" to list available operations.'
    }


def test_registered_root_returns_contextual_api_error(monkeypatch):
    class BrokenClient:
        def get(self, _path: str):
            raise APIError(503, "GET", "/api/health?token=secret", {"detail": "unavailable"})

    monkeypatch.setattr(tools, "_get_client", lambda: BrokenClient())

    result = _registered("casdoor_version")()

    assert result["error"].startswith("GET /api/health -> 503")
    assert "secret" not in result["error"]


def test_registered_tool_redacts_transport_query_values(monkeypatch):
    request = httpx.Request("GET", "https://casdoor.example/api/users?access_token=secret")
    monkeypatch.setattr(
        server,
        "_dispatch",
        lambda *_args: _raise(httpx.ConnectError("connection refused", request=request)),
    )

    result = _registered("casdoor_read")("ListUsers", {})

    assert "Casdoor transport failure: GET /api/users: ConnectError" in result["error"]
    assert "secret" not in result["error"]
    assert "access_token=" not in result["error"]


def test_registered_tool_returns_missing_parameter_error():
    result = _registered("casdoor_read")("ListUsers", {})

    assert result["error"] == "Missing required parameters: ['owner']"


def test_registered_tool_rejects_unknown_parameters():
    result = _registered("casdoor_read")(
        "ListUsers", {"owner": "built-in", "unexpected": "value"}
    )

    assert result == {"error": "Invalid parameters: ['unexpected']"}


def test_coerce_call_preserves_defaults_and_named_coercion():
    def operation(
        enabled: bool = False, scope: Literal["all", "active"] = "all"
    ) -> tuple[bool, str]:
        return enabled, scope

    assert server._coerce_call(operation, {}) == (False, "all")
    assert server._coerce_call(operation, {"enabled": "yes", "scope": "active"}) == (
        True,
        "active",
    )


def test_registration_keeps_tools_sync():
    """MCP classifies tools with `iscoroutinefunction`; every op here is sync,
    so the wrapper must not make the SDK await them on the event loop."""
    assert all(not t.is_async for t in server.mcp._tool_manager._tools.values())


def test_registered_root_preserves_success_shape(monkeypatch):
    class OkClient:
        def get(self, _path: str):
            return {"status": "ok"}

    monkeypatch.setattr(tools, "_get_client", lambda: OkClient())

    result = _registered("casdoor_version")()

    assert result["service"] == {"status": "ok"}
    assert "mcp" in result


def test_registered_tool_propagates_programming_error(monkeypatch):
    monkeypatch.setattr(
        server, "_dispatch", lambda *_args: _raise(AttributeError("programming error"))
    )

    with pytest.raises(AttributeError):
        _registered("casdoor_read")("ListUsers", {"owner": "built-in"})


def test_error_text_redacts_secret_fields():
    """Container values are redacted whole: a partial match would leave the
    tail of a list or nested dict in the reported error."""
    text = server._redact_error_text(
        {"password": ["too short", "p@ssw0rd"], "api_secret": "zzz", "detail": "keep me"}
    )

    assert "p@ssw0rd" not in text
    assert "zzz" not in text
    assert "keep me" in text
