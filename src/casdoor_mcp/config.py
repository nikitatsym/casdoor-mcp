from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    casdoor_endpoint: str = ""
    casdoor_client_id: str = ""
    casdoor_client_secret: str = ""
    casdoor_access_token: str = ""
    casdoor_access_key: str = ""
    casdoor_access_secret: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _reset_settings() -> None:
    """Force re-read from env. Used by tests."""
    global _settings
    _settings = None
