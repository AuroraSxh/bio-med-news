from collections.abc import Iterable
import re

from app.core.categories import CATEGORIES
from app.schemas.pipeline import CandidateNewsItem


KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Financing",
        (
            "series a",
            "series b",
            "series c",
            "series d",
            "seed financing",
            "financing",
            "funding",
            "raises",
            "raised",
            "ipo",
            "public offering",
            "private placement",
            "loan",
            "debt",
            "venture round",
        ),
    ),
    (
        "Clinical/Regulatory Progress",
        (
            "fda",
            "ema",
            "nmpa",
            "mhra",
            "ind",
            "cta",
            "bla",
            "nda",
            "clinical trial",
            "phase 1",
            "phase i",
            "phase 2",
            "phase ii",
            "phase 3",
            "phase iii",
            "approval",
            "approved",
            "clearance",
            "cleared",
            "crl",
            "clinical hold",
            "topline",
            "interim",
            "orphan drug",
            "fast track",
            "breakthrough therapy",
        ),
    ),
    (
        "Partnership/Licensing",
        (
            "partnership",
            "collaboration",
            "collaborate",
            "licensing",
            "license",
            "option agreement",
            "co-develop",
            "co-development",
            "alliance",
            "strategic agreement",
            "research agreement",
        ),
    ),
    (
        "M&A/Organization",
        (
            "acquisition",
            "acquires",
            "acquired",
            "merger",
            "merge",
            "divest",
            "restructuring",
            "layoff",
            "workforce reduction",
            "appoints",
            "appointment",
            "ceo",
            "chief executive",
            "organization",
        ),
    ),
    (
        "Manufacturing/CMC",
        (
            "manufacturing",
            "cmc",
            "cdmo",
            "facility",
            "plant",
            "scale-up",
            "scale up",
            "vector",
            "viral vector",
            "process development",
            "quality system",
            "gmp",
            "fill-finish",
            "capacity",
        ),
    ),
    (
        "Policy/Industry Environment",
        (
            "policy",
            "guidance",
            "reimbursement",
            "cms",
            "rule",
            "draft recommendations",
            "industry environment",
            "guideline",
            "medicare",
            "pricing reform",
            "tariff",
        ),
    ),
    (
        "R&D",
        (
            "preclinical",
            "research",
            "platform",
            "target discovery",
            "engineered",
            "discovery",
            "study",
            "mechanism",
            "pipeline",
            "proof-of-concept",
            "in vivo",
            "in vitro",
            "publication",
        ),
    ),
]


def classify_with_rules(item: CandidateNewsItem) -> tuple[str, bool]:
    haystack = " ".join(
        value.casefold()
        for value in [item.title, item.raw_summary or "", item.content_text or ""]
        if value
    )
    matches: dict[str, int] = {}
    for category, keywords in KEYWORD_RULES:
        score = sum(1 for keyword in keywords if _keyword_matches(haystack, keyword))
        if score:
            matches[category] = score

    if not matches:
        return "Other", True
    ordered_matches = sorted(
        matches.items(),
        key=lambda match: (-match[1], _category_priority(match[0])),
    )
    top_category, top_score = ordered_matches[0]
    ambiguous = len(ordered_matches) > 1 and ordered_matches[1][1] >= top_score
    return top_category, ambiguous


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        return "Other"
    return category


def category_counts(categories: Iterable[str]) -> dict[str, int]:
    counts = {category: 0 for category in CATEGORIES}
    for category in categories:
        counts[validate_category(category)] += 1
    return counts


def _keyword_matches(haystack: str, keyword: str) -> bool:
    if len(keyword) <= 4 and keyword.isalnum():
        return re.search(rf"\b{re.escape(keyword)}\b", haystack) is not None
    return keyword in haystack


def _category_priority(category: str) -> int:
    try:
        return [rule_category for rule_category, _ in KEYWORD_RULES].index(category)
    except ValueError:
        return len(KEYWORD_RULES)
