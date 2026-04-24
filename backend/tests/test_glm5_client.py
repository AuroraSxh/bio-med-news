import httpx
import pytest

from app.services.glm5_client import _extract_json_object, _is_retryable_http_error


class TestExtractJsonObject:
    def test_plain_json(self):
        content = '{"key": "value", "num": 42}'
        result = _extract_json_object(content)
        assert result == {"key": "value", "num": 42}

    def test_json_in_markdown_code_block(self):
        content = '```json\n{"key": "value"}\n```'
        result = _extract_json_object(content)
        assert result == {"key": "value"}

    def test_json_in_plain_code_block(self):
        content = '```\n{"key": "value"}\n```'
        result = _extract_json_object(content)
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        content = 'Here is the result:\n{"key": "value"}\nEnd of response.'
        result = _extract_json_object(content)
        assert result == {"key": "value"}

    def test_no_json_raises_valueerror(self):
        with pytest.raises(ValueError, match="did not contain a JSON object"):
            _extract_json_object("No JSON here at all")

    def test_non_dict_json_raises_valueerror(self):
        with pytest.raises(ValueError, match="did not contain a JSON object"):
            _extract_json_object("[1, 2, 3]")

    def test_nested_json(self):
        content = '{"outer": {"inner": "value"}, "list": [1, 2]}'
        result = _extract_json_object(content)
        assert result["outer"]["inner"] == "value"
        assert result["list"] == [1, 2]

    def test_whitespace_handling(self):
        content = "   \n  {\"key\": \"value\"}  \n  "
        result = _extract_json_object(content)
        assert result == {"key": "value"}


class TestRetryableHttpErrors:
    def test_connect_timeout_is_retryable(self):
        exc = httpx.ConnectTimeout("timeout")
        assert _is_retryable_http_error(exc, None) is True

    def test_429_is_retryable(self):
        request = httpx.Request("POST", "https://example.com")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("too many requests", request=request, response=response)
        assert _is_retryable_http_error(exc, 429) is True

    def test_401_is_not_retryable(self):
        request = httpx.Request("POST", "https://example.com")
        response = httpx.Response(401, request=request)
        exc = httpx.HTTPStatusError("unauthorized", request=request, response=response)
        assert _is_retryable_http_error(exc, 401) is False
