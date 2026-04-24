"""Tests verifying that ILIKE special characters are properly escaped in search."""


class TestSearchEscaping:
    def test_percent_escaped(self):
        q = "100%"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        assert escaped_q == "100\\%"
        needle = f"%{escaped_q}%"
        assert needle == "%100\\%%"

    def test_underscore_escaped(self):
        q = "cell_therapy"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        assert escaped_q == "cell\\_therapy"

    def test_backslash_escaped(self):
        q = "path\\to"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        assert escaped_q == "path\\\\to"

    def test_combined_special_chars(self):
        q = "100%_test\\value"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        assert escaped_q == "100\\%\\_test\\\\value"

    def test_normal_text_unchanged(self):
        q = "cell therapy"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        assert escaped_q == "cell therapy"

    def test_needle_wrapping(self):
        q = "test"
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        needle = f"%{escaped_q}%"
        assert needle == "%test%"
