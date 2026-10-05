import logging
from contextlib import contextmanager

from psycopg import OperationalError

import app.main as main_module


def test_database_error_is_logged_but_response_stays_safe(caplog):
    error = OperationalError("private database diagnostic")

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        response = main_module.database_error_handler(None, error)

    assert response.status_code == 503
    assert response.body == b'{"detail":"Database unavailable"}'
    assert "Database operation failed" in caplog.text
    assert "private database diagnostic" in caplog.text


def test_health_reports_database_readiness(context):
    client, _, _ = context
    assert client.get("/health").json() == {"status": "ok", "database": True}


def test_health_remains_live_when_database_is_unavailable(
    context, monkeypatch, caplog
):
    client, _, _ = context

    @contextmanager
    def unavailable_connection():
        raise OperationalError("readiness failure")
        yield

    monkeypatch.setattr(main_module, "connection", unavailable_connection)
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": False}
    assert "Database readiness check failed" in caplog.text
