"""Drug synonym expansion for tracked products.

Loads a curated synonym registry at import time and provides `expand_aliases`
which, given a user-supplied display name + aliases, returns the deduplicated
union with any known synonym group members folded in.

Matching is performed on an alphanumeric-only, case-folded key so that
variants like ``AZD-0120``, ``AZD0120`` and ``azd 0120`` collapse together.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from app.services.glm5_client import GLM5Client

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "drug_synonyms.json"
_MAX_ALIASES = 25


def _alnum_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _load_groups() -> list[list[str]]:
    try:
        with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        logger.warning("drug synonyms file not found at %s", _CONFIG_PATH)
        return []
    except json.JSONDecodeError as exc:
        logger.error("failed to parse drug synonyms: %s", exc)
        return []
    groups = raw.get("groups") if isinstance(raw, dict) else raw
    if not isinstance(groups, list):
        return []
    out: list[list[str]] = []
    for group in groups:
        if isinstance(group, list):
            names = [str(x).strip() for x in group if isinstance(x, str) and str(x).strip()]
            if names:
                out.append(names)
    return out


_RAW_GROUPS: list[list[str]] = _load_groups()
# Each group as frozenset of alnum keys (used for lookup membership).
CANONICAL_GROUPS: list[frozenset[str]] = [
    frozenset(_alnum_key(name) for name in group if _alnum_key(name))
    for group in _RAW_GROUPS
]
# Map: alnum-key -> index into _RAW_GROUPS.
_KEY_TO_GROUP_INDEX: dict[str, int] = {}
for idx, group in enumerate(_RAW_GROUPS):
    for name in group:
        key = _alnum_key(name)
        if key and key not in _KEY_TO_GROUP_INDEX:
            _KEY_TO_GROUP_INDEX[key] = idx


def find_group(name: str) -> list[str] | None:
    """Return the original-casing list of synonyms for ``name``, else None."""
    key = _alnum_key(name)
    if not key:
        return None
    idx = _KEY_TO_GROUP_INDEX.get(key)
    if idx is None:
        return None
    return list(_RAW_GROUPS[idx])


def _normalize_user_aliases(aliases: Iterable[str]) -> list[str]:
    """Trim whitespace, drop empties, dedupe by alnum key (preserve first casing)."""
    seen: set[str] = set()
    out: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str):
            continue
        stripped = alias.strip()
        if not stripped:
            continue
        key = _alnum_key(stripped)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(stripped)
    return out


def expand_aliases(
    display_name: str,
    user_aliases: list[str],
    *,
    glm5_client: "GLM5Client | None" = None,
    company_name: str | None = None,
    indications: list[str] | None = None,
    modality: str | None = None,
) -> list[str]:
    """Expand a display name + user-supplied aliases with known synonym groups.

    The returned list:
      * preserves ``display_name`` verbatim at index 0 (when non-empty),
      * then lists user-provided aliases (normalized / deduped),
      * then appends any additional synonym-group members (original case),
      * deduplicated by alnum-key,
      * capped at :data:`_MAX_ALIASES` entries.
    """
    display_name = (display_name or "").strip()
    normalized_user = _normalize_user_aliases(user_aliases or [])

    ordered: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        stripped = name.strip()
        if not stripped:
            return
        key = _alnum_key(stripped)
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(stripped)

    if display_name:
        _add(display_name)
    for alias in normalized_user:
        _add(alias)

    # Expand via synonym groups for each current entry.
    for seed in [display_name, *normalized_user]:
        group = find_group(seed)
        if not group:
            continue
        for member in group:
            if len(ordered) >= _MAX_ALIASES:
                break
            _add(member)
        if len(ordered) >= _MAX_ALIASES:
            break

    # If the static synonym registry produced little/nothing beyond the user's
    # own input, optionally consult the LLM for additional aliases. We trigger
    # this when the post-static result has at most 2 entries beyond the
    # display_name (i.e. the registry had no hit for an uncommon code).
    extras_count = max(0, len(ordered) - (1 if display_name else 0))
    if glm5_client is not None and extras_count <= 2 and display_name:
        try:
            suggestions = glm5_client.suggest_product_aliases(
                display_name=display_name,
                company_name=company_name,
                indications=list(indications or []),
                modality=modality,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LLM alias suggestion raised: %s", exc)
            suggestions = None

        if suggestions:
            for member in suggestions:
                if len(ordered) >= _MAX_ALIASES:
                    break
                _add(member)

        logger.info(
            "expand_aliases LLM augmentation",
            extra={
                "display_name": display_name,
                "llm_suggestions": list(suggestions) if suggestions else [],
                "final_aliases": list(ordered[:_MAX_ALIASES]),
            },
        )

    return ordered[:_MAX_ALIASES]


__all__ = ["expand_aliases", "find_group", "CANONICAL_GROUPS"]
