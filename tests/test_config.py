import os

from casdoor_mcp.config import Settings, _reset_settings, get_settings


def test_defaults():
    _reset_settings()
    s = Settings()
    assert s.casdoor_endpoint == ""
    assert s.casdoor_client_id == ""
    assert s.casdoor_client_secret == ""
    assert s.casdoor_access_token == ""
    assert s.casdoor_access_key == ""
    assert s.casdoor_access_secret == ""


def test_env_vars(monkeypatch):
    _reset_settings()
    monkeypatch.setenv("CASDOOR_ENDPOINT", "https://example.com")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csecret")
    s = Settings()
    assert s.casdoor_endpoint == "https://example.com"
    assert s.casdoor_client_id == "cid"
    assert s.casdoor_client_secret == "csecret"


def test_singleton():
    _reset_settings()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_reset():
    _reset_settings()
    s1 = get_settings()
    _reset_settings()
    s2 = get_settings()
    assert s1 is not s2
