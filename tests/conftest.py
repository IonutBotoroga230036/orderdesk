from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh database with sample master data and the five sample emails ingested."""
    monkeypatch.setenv("ORDERDESK_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("ORDERDESK_EXTRACTOR", "heuristic")
    monkeypatch.setenv("ORDERDESK_MAIL_SOURCE", "folder")
    monkeypatch.setenv("ORDERDESK_INBOX_DIR", str(SAMPLE / "emails"))
    monkeypatch.setenv("ORDERDESK_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("ORDERDESK_UI_PASSWORD", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from orderdesk.config import get_settings
    from orderdesk.db import init_db, reset_engine, session_scope
    from orderdesk.ingest import get_mail_source, ingest
    from orderdesk.seed import load_master_data

    get_settings.cache_clear()
    reset_engine()
    init_db(drop=True)
    with session_scope() as s:
        load_master_data(s, SAMPLE)
        ingest(s, get_mail_source())
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def session(env):
    from orderdesk.db import new_session

    s = new_session()
    yield s
    s.close()


def email_by_subject(session, subject):
    from sqlalchemy import select

    from orderdesk.models import Email

    return session.scalar(select(Email).where(Email.subject == subject))
