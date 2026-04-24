import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_log_format_is_restricted():
    with pytest.raises(ValidationError):
        Settings(LOG_FORMAT="xml")


def test_retry_attempt_bounds_are_validated():
    with pytest.raises(ValidationError):
        Settings(GLM5_REQUEST_MAX_ATTEMPTS=0)

    with pytest.raises(ValidationError):
        Settings(SOURCE_REQUEST_MAX_ATTEMPTS=8)
