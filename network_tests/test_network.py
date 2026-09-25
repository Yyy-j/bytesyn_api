from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_fastapi_app_starts() -> None:
    with TestClient(app):
        assert app.title == "BYTESYNC API"


def test_health_is_a_database_independent_liveness_check(monkeypatch) -> None:
    for name in (
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


def test_container_binds_all_interfaces() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--port", "8000"' in dockerfile
    assert '"--host", "127.0.0.1"' not in dockerfile
