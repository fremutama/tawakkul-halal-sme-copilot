import pytest, agent


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    """Tests write their audit log to a temp folder, never to the repo's evidence/ folder."""
    monkeypatch.setattr(agent, "LOG", tmp_path / "audit_log.jsonl")
