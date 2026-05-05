from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
project_root_str = str(PROJECT_ROOT)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from app.db import reset_database_state  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_test_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep automated tests away from the user's local SQLite database."""

    database_path = tmp_path / "resume-agent-test.db"
    monkeypatch.setenv("RESUME_AGENT_DB_URL", f"sqlite:///{database_path}")
    reset_database_state()
    yield
    reset_database_state()
