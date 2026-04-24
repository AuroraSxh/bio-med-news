import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_preserves_extra_fields():
    formatter = JsonFormatter()
    record = logging.makeLogRecord(
        {
            "name": "app.test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "hello",
            "source_name": "GEN",
            "status_code": 429,
            "retryable": True,
        }
    )

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello"
    assert payload["source_name"] == "GEN"
    assert payload["status_code"] == 429
    assert payload["retryable"] is True
