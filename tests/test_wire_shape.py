"""Regression tests for request shapes the conformance test structurally cannot hold.

`test_swagger_conformance.py` checks that every name we send is a name Casdoor
accepts. It cannot check the two things that actually broke here, because the
spec does not encode either one:

- `id` is optional on `POST /api/update-user` (upstream also accepts `userId` or
  the session user), yet this MCP supplies neither alternative, so omitting `id`
  would silently retarget the update;
- Casdoor declares no `required` array on any definition, so nothing in the spec
  says a delete body must carry `organization` / `application`, or that an
  update body must be the whole object rather than a sparse patch.

These pin the wire shape directly instead, driving the real ops through a
`httpx.MockTransport` so no Casdoor instance is involved.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from casdoor_mcp import client, tools
from casdoor_mcp.client import APIError
from casdoor_mcp.config import _reset_settings

# op name -> (get path, update path) for the read-modify-write pairs.
UPDATE_OPS = {
    "update_user": ("/api/get-user", "/api/update-user"),
    "update_organization": ("/api/get-organization", "/api/update-organization"),
    "update_application": ("/api/get-application", "/api/update-application"),
    "update_provider": ("/api/get-provider", "/api/update-provider"),
    "update_role": ("/api/get-role", "/api/update-role"),
    "update_permission": ("/api/get-permission", "/api/update-permission"),
    "update_group": ("/api/get-group", "/api/update-group"),
}


class _Wire:
    """Records every outbound request and answers GETs from a canned object."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.current: Any = {"owner": "built-in", "name": "alice"}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": self.current})
        return httpx.Response(200, json={"status": "ok", "data": "Affected"})

    def sent(self, method: str, path: str) -> httpx.Request:
        found = [r for r in self.requests if r.method == method and r.url.path == path]
        assert len(found) == 1, f"expected exactly one {method} {path}, got {len(found)}"
        return found[0]

    @staticmethod
    def body(request: httpx.Request) -> dict:
        return json.loads(request.content)


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> _Wire:
    recorder = _Wire()
    real_client = httpx.Client

    def patched(**kwargs: Any) -> httpx.Client:
        return real_client(transport=httpx.MockTransport(recorder.handle), **kwargs)

    _reset_settings()
    monkeypatch.setenv("CASDOOR_ENDPOINT", "https://casdoor.example.com")
    monkeypatch.setenv("CASDOOR_ACCESS_TOKEN", "t0ken")
    monkeypatch.setattr(client.httpx, "Client", patched)
    # The client is a module singleton; drop it so the patched transport is used.
    monkeypatch.setattr(tools, "_client", None)
    return recorder


@pytest.mark.parametrize("op", sorted(UPDATE_OPS))
def test_update_selects_the_row_by_id_on_both_calls(wire: _Wire, op: str) -> None:
    """Casdoor identifies the row to update by the `id` query param only; body
    owner/name select nothing, so a missing `id` is a silent no-op or, for
    update-user, an update of whoever the session belongs to."""
    get_path, update_path = UPDATE_OPS[op]
    getattr(tools, op)("built-in", "alice")

    assert wire.sent("GET", get_path).url.params["id"] == "built-in/alice"
    assert wire.sent("POST", update_path).url.params["id"] == "built-in/alice"


@pytest.mark.parametrize("op", sorted(UPDATE_OPS))
def test_update_reads_then_merges_over_the_current_object(wire: _Wire, op: str) -> None:
    """Casdoor rewrites every column, so the body must be the whole object with
    the caller's changes laid over it - a sparse body blanks the rest."""
    update_path = UPDATE_OPS[op][1]
    wire.current = {
        "owner": "built-in",
        "name": "alice",
        "displayName": "Old Name",
        "keepMe": "untouched",
    }
    getattr(tools, op)("built-in", "alice", displayName="New Name")

    assert wire.requests[0].method == "GET", "the read must precede the write"
    body = wire.body(wire.sent("POST", update_path))
    assert body["displayName"] == "New Name"
    assert body["keepMe"] == "untouched", "read-modify-write dropped a field"
    assert (body["owner"], body["name"]) == ("built-in", "alice")


@pytest.mark.parametrize("op", sorted(UPDATE_OPS))
def test_update_refuses_when_the_object_is_missing(wire: _Wire, op: str) -> None:
    """Falling through to a sparse POST here would blank every column of a row
    the caller never meant to touch, so the read must fail the call outright."""
    _, update_path = UPDATE_OPS[op]
    wire.current = None

    with pytest.raises(APIError):
        getattr(tools, op)("built-in", "ghost")

    assert not [r for r in wire.requests if r.url.path == update_path]


def test_delete_session_sends_the_application(wire: _Wire) -> None:
    """Session rows are keyed by owner/name/application; a partial key deletes
    nothing while still answering 200."""
    tools.delete_session("built-in", "alice", "app-built-in")

    body = wire.body(wire.sent("POST", "/api/delete-session"))
    assert body == {"owner": "built-in", "name": "alice", "application": "app-built-in"}


def test_delete_token_sends_the_organization(wire: _Wire) -> None:
    """Casdoor filters the token delete by organization; without it the query
    matches no row and still answers 200."""
    tools.delete_token("admin", "token-1", "built-in")

    body = wire.body(wire.sent("POST", "/api/delete-token"))
    assert body == {"owner": "admin", "name": "token-1", "organization": "built-in"}
