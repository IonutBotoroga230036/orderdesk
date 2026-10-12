from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ORDERDESK_", extra="ignore")

    database_url: str = "sqlite:///./orderdesk.db"

    extractor: str = "claude"  # claude | heuristic
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "ORDERDESK_ANTHROPIC_API_KEY")
    )
    anthropic_model: str = "claude-sonnet-5-5"

    mail_source: str = "folder"  # folder | imap | graph
    inbox_dir: Path = Path("data/sample/emails")
    imap_host: str | None = None
    imap_user: str | None = None
    imap_password: str | None = None
    imap_folder: str = "INBOX"
    graph_tenant_id: str | None = None
    graph_client_id: str | None = None
    graph_client_secret: str | None = None
    graph_mailbox: str | None = None

    erp: str = "csv"  # csv | exact
    export_dir: Path = Path("exports")
    exact_base_url: str = "https://start.exactonline.nl"
    exact_division: int | None = None
    exact_access_token: str | None = None

    poll_seconds: int = 60
    ui_user: str | None = None
    ui_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
