from unittest.mock import MagicMock, patch

from casdoor_mcp.config import _reset_settings
from casdoor_mcp.tools import (
    _data,
    _slim,
    _slim_list,
    _SLIM_USER_FIELDS,
    _SLIM_ORGANIZATION_FIELDS,
    _SLIM_APPLICATION_FIELDS,
)


def test_data_unwrap():
    assert _data({"data": [1, 2]}) == [1, 2]
    assert _data({"status": "ok"}) == {"status": "ok"}
    assert _data(None) is None
    assert _data([1, 2]) == [1, 2]


def test_slim():
    item = {"owner": "org", "name": "alice", "extra": "ignored", "displayName": "Alice"}
    result = _slim(item, {"owner", "name"})
    assert result == {"owner": "org", "name": "alice"}


def test_slim_list():
    items = [
        {"owner": "org", "name": "alice", "email": "a@b.c", "extra": "x"},
        {"owner": "org", "name": "bob", "email": "b@b.c", "phone": "123"},
    ]
    result = _slim_list(items, {"owner", "name", "email"})
    assert len(result) == 2
    assert result[0] == {"owner": "org", "name": "alice", "email": "a@b.c"}
    assert result[1] == {"owner": "org", "name": "bob", "email": "b@b.c"}


def test_slim_list_non_list():
    assert _slim_list(None, {"a"}) is None
    assert _slim_list("hello", {"a"}) == "hello"


def test_slim_fields_defined():
    assert "owner" in _SLIM_USER_FIELDS
    assert "name" in _SLIM_USER_FIELDS
    assert "displayName" in _SLIM_ORGANIZATION_FIELDS
    assert "organization" in _SLIM_APPLICATION_FIELDS


def test_auth_priority_token(monkeypatch):
    """Access token takes priority over client_id+secret."""
    _reset_settings()
    monkeypatch.setenv("CASDOOR_ENDPOINT", "https://example.com")
    monkeypatch.setenv("CASDOOR_ACCESS_TOKEN", "mytoken")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csecret")

    with patch("casdoor_mcp.client.httpx.Client") as mock_client:
        from casdoor_mcp.client import CasdoorClient
        c = CasdoorClient()
        call_kwargs = mock_client.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer mytoken"
        assert call_kwargs.kwargs["params"] == {}


def test_auth_priority_client_id(monkeypatch):
    """Client ID+secret used when no access token."""
    _reset_settings()
    monkeypatch.setenv("CASDOOR_ENDPOINT", "https://example.com")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csecret")

    with patch("casdoor_mcp.client.httpx.Client") as mock_client:
        from casdoor_mcp.client import CasdoorClient
        c = CasdoorClient()
        call_kwargs = mock_client.call_args
        assert call_kwargs.kwargs["params"] == {"clientId": "cid", "clientSecret": "csecret"}
        assert "Authorization" not in call_kwargs.kwargs["headers"]


def test_auth_priority_access_key(monkeypatch):
    """Access key+secret used when no token or client_id."""
    _reset_settings()
    monkeypatch.setenv("CASDOOR_ENDPOINT", "https://example.com")
    monkeypatch.setenv("CASDOOR_ACCESS_KEY", "akey")
    monkeypatch.setenv("CASDOOR_ACCESS_SECRET", "asecret")

    with patch("casdoor_mcp.client.httpx.Client") as mock_client:
        from casdoor_mcp.client import CasdoorClient
        c = CasdoorClient()
        call_kwargs = mock_client.call_args
        assert call_kwargs.kwargs["params"] == {"accessKey": "akey", "accessSecret": "asecret"}
        assert "Authorization" not in call_kwargs.kwargs["headers"]


def test_dispatch_help():
    """Importing server registers tools; help dispatch works."""
    from casdoor_mcp.server import _build_help, _group_ops
    assert "casdoor_read" in _group_ops
    help_text = _build_help("casdoor_read")
    assert "ListUsers" in help_text
    assert "ListOrganizations" in help_text
