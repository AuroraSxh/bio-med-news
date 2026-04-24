"""Corporate dynamics tagging for cell-therapy companies.

Matches news items to a curated set of companies and detects three kinds of
signals (layoffs/restructuring, new pipeline/IND, financing/valuation) from
item text using simple substring rules over a lowercased, alnum-stripped
haystack (consistent with product_tracking._alnum_key).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Canonical signal bucket names exposed in the API and to the frontend.
CORPORATE_SIGNAL_RULES: dict[str, tuple[str, ...]] = {
    "layoffs": (
        "layoff", "layoffs", "restructuring", "workforce reduction",
        "cut workforce", "cuts workforce", "shut down", "wind down",
        "discontinue",
        "裁员", "重组", "关停", "削减", "停止开发", "终止",
    ),
    "new_pipeline": (
        "new IND", "IND approval", "IND filing", "IND cleared",
        "pipeline expansion", "new program", "new candidate",
        "first patient dosed", "first-in-human",
        "新管线", "IND获批", "IND申报", "首例给药", "首次人体", "新项目",
    ),
    "financing": (
        "Series A", "Series B", "Series C", "Series D", "IPO", "valuation",
        "raised", "fundraise", "fundraising", "closed financing",
        "融资", "上市", "估值", "募资", "轮融资", "pre-IPO",
    ),
}


def _alnum_key(value: str | None) -> str:
    """Lowercase + strip to alnum (Unicode-friendly via \\w)."""
    if not value:
        return ""
    # Keep unicode word chars (covers CJK) and digits, strip everything else.
    return re.sub(r"[^\w]+", "", value.casefold())


def _load_companies() -> list[dict[str, Any]]:
    config_path = (
        Path(__file__).resolve().parents[2] / "config" / "cell_therapy_companies.json"
    )
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("cell_therapy_companies.json not found at %s", config_path)
        return []
    except json.JSONDecodeError as exc:
        logger.error("failed to parse cell_therapy_companies.json: %s", exc)
        return []

    normalized: list[dict[str, Any]] = []
    for entry in data:
        name = entry.get("name")
        if not name:
            continue
        aliases = list(entry.get("aliases") or [])
        # Always include canonical + chinese name as aliases for matching.
        chinese_name = entry.get("chinese_name") or ""
        all_terms = [name, chinese_name, *aliases]
        # Precompute alnum-normalized match keys; filter out too-short to avoid
        # false positives (e.g. "AZ" -> ok, very short keys are risky though).
        alias_keys: list[str] = []
        seen: set[str] = set()
        for term in all_terms:
            key = _alnum_key(term)
            if len(key) >= 2 and key not in seen:
                seen.add(key)
                alias_keys.append(key)
        normalized.append({
            "name": name,
            "chinese_name": chinese_name,
            "aliases": aliases,
            "domain_hint": entry.get("domain_hint") or "",
            "_alias_keys": alias_keys,
        })
    return normalized


# Loaded once at import time.
CELL_THERAPY_COMPANIES: list[dict[str, Any]] = _load_companies()


def get_company(name: str) -> dict[str, Any] | None:
    for company in CELL_THERAPY_COMPANIES:
        if company["name"] == name:
            return company
    return None


def match_company(text: str) -> str | None:
    """Return canonical company name whose alias appears in ``text``.

    Uses alnum-stripped haystack (same pattern as product_tracking._alnum_key).
    Returns the FIRST match found (companies are checked in config order).
    """
    if not text:
        return None
    haystack = _alnum_key(text)
    if not haystack:
        return None
    for company in CELL_THERAPY_COMPANIES:
        for key in company["_alias_keys"]:
            if key and len(key) >= 2 and key in haystack:
                return company["name"]
    return None


def detect_corporate_signals(text: str) -> list[str]:
    """Return the list of signal buckets whose keyword list matches ``text``.

    Matching is case-insensitive substring on the raw lowercased text (so
    phrases with spaces like "Series A" still match).
    """
    if not text:
        return []
    lowered = text.casefold()
    matched: list[str] = []
    for bucket, terms in CORPORATE_SIGNAL_RULES.items():
        for term in terms:
            if term.casefold() in lowered:
                matched.append(bucket)
                break
    return matched
