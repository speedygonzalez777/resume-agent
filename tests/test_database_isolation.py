from pathlib import Path

from app.db.database import get_database_url


def test_tests_do_not_use_default_local_sqlite_database() -> None:
    database_url = get_database_url()
    local_database_path = (Path(__file__).resolve().parents[1] / "data" / "resume_agent.db").as_posix()

    assert local_database_path not in database_url
    assert "data/resume_agent.db" not in database_url
