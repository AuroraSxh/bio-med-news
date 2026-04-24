from pathlib import Path

from app.core.config import get_settings
from app.services.sources import canonicalize_url, clean_text, load_sources


class TestCanonicalizeUrl:
    def test_removes_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&id=42"
        result = canonicalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=42" in result

    def test_removes_fbclid(self):
        url = "https://example.com/page?fbclid=abc123&key=val"
        result = canonicalize_url(url)
        assert "fbclid" not in result
        assert "key=val" in result

    def test_removes_gclid(self):
        url = "https://example.com/?gclid=xyz"
        result = canonicalize_url(url)
        assert "gclid" not in result

    def test_normalizes_trailing_slash(self):
        assert canonicalize_url("https://example.com/path/") == canonicalize_url("https://example.com/path")

    def test_lowercases_scheme_and_host(self):
        result = canonicalize_url("HTTPS://EXAMPLE.COM/Path")
        assert result.startswith("https://example.com/")
        assert "/Path" in result

    def test_sorts_query_params(self):
        url1 = "https://example.com/?b=2&a=1"
        url2 = "https://example.com/?a=1&b=2"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_strips_whitespace(self):
        result = canonicalize_url("  https://example.com/article  ")
        assert result == "https://example.com/article"

    def test_root_path_preserved(self):
        result = canonicalize_url("https://example.com")
        assert result.endswith("/")


class TestCleanText:
    def test_strips_html_tags(self):
        result = clean_text("<p>Hello <b>world</b></p>")
        assert result == "Hello world"

    def test_decodes_html_entities(self):
        result = clean_text("AT&amp;T &lt;Corp&gt;")
        assert result == "AT&T <Corp>"

    def test_normalizes_whitespace(self):
        result = clean_text("  hello   world  \n  foo  ")
        assert result == "hello world foo"

    def test_returns_none_for_empty(self):
        assert clean_text("") is None
        assert clean_text(None) is None

    def test_returns_none_for_whitespace_only(self):
        assert clean_text("   ") is None

    def test_complex_html(self):
        html = '<div class="content"><p>First paragraph.</p><br/><p>Second.</p></div>'
        result = clean_text(html)
        assert "First paragraph." in result
        assert "Second." in result
        assert "<" not in result


class TestLoadSources:
    def test_load_sources_from_env_json(self, monkeypatch):
        monkeypatch.setenv(
            "INGESTION_SOURCES_JSON",
            '[{"name":"Test Feed","feed_url":"https://example.com/rss.xml","max_items":5}]',
        )
        get_settings.cache_clear()
        sources = load_sources()
        assert len(sources) == 1
        assert sources[0].name == "Test Feed"
        assert str(sources[0].feed_url) == "https://example.com/rss.xml"

    def test_load_sources_from_config_path(self, monkeypatch, tmp_path: Path):
        source_file = tmp_path / "sources.json"
        source_file.write_text(
            '[{"name":"GEN","feed_url":"https://example.com/feed/","max_items":3}]',
            encoding="utf-8",
        )
        monkeypatch.delenv("INGESTION_SOURCES_JSON", raising=False)
        monkeypatch.setenv("SOURCE_CONFIG_PATH", str(source_file))
        get_settings.cache_clear()
        sources = load_sources()
        assert len(sources) == 1
        assert sources[0].max_items == 3
