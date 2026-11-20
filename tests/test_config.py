import shutil

from conftest import ROOT


def test_settings_load_from_env_example_as_is(tmp_path, monkeypatch):
    """A fresh `copy .env.example .env` must start without editing (blank values mean 'not set')."""
    shutil.copy(ROOT / ".env.example", tmp_path / ".env")
    monkeypatch.chdir(tmp_path)
    for key in list(__import__("os").environ):
        if key.startswith("TICKWELL_") or key == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(key)

    from tickwell.config import Settings

    s = Settings()
    assert s.exact_division is None
    assert s.ollama_model is None
    assert s.ollama_num_ctx == 16384
    assert s.local_only is False
    assert s.extractor == "claude"
