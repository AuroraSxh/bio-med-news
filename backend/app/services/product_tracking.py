import hashlib
import logging
import re
import threading
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.orm import Session

from app.models import NewsItem, TrackedProduct
from app.schemas.pipeline import CandidateNewsItem
from app.schemas.products import ProductNewsMatch, ProductTimelineEventDraft, ProductTimelineExtraction
from app.services.enrichment import enrich_items, normalize_title
from app.services.glm5_client import GLM5Client
from app.services.news_repository import upsert_news_items
from app.services.product_repository import (
    list_linked_news_for_product,
    mark_product_backfilled,
    search_news_candidates_for_product,
    upsert_product_news_link,
    upsert_product_timeline_event,
)
from app.services.sources import USER_AGENT, canonicalize_url, clean_text

logger = logging.getLogger(__name__)

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_ARTICLE_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
CLINICALTRIALS_SEARCH_URL = "https://clinicaltrials.gov/api/v2/studies"
CLINICALTRIALS_STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"
MAX_QUERY_COUNT = 4
MAX_RESULTS_PER_QUERY = 10


class ProductBackfillResult:
    def __init__(self, fetched_candidates: int, linked_news_count: int, created_timeline_events: int) -> None:
        self.fetched_candidates = fetched_candidates
        self.linked_news_count = linked_news_count
        self.created_timeline_events = created_timeline_events


BACKFILL_DEADLINE_SECONDS = 420  # LLM timeline extraction is ~25s per linked news item; 5 items × 25s + overhead fits here.


def _deadline_enforcer(product_id: int, done_event: threading.Event) -> None:
    """Runs on a Timer thread; if backfill hasn't signalled done, flip status to failed."""
    if done_event.is_set():
        return
    from sqlalchemy.orm import Session as _Session

    from app.db import engine as _engine

    try:
        with _Session(_engine) as db:
            product = db.get(TrackedProduct, product_id)
            if product is None:
                return
            if product.backfill_status == "running":
                product.backfill_status = "failed"
                product.backfill_error = f"backfill exceeded {BACKFILL_DEADLINE_SECONDS}s deadline"
                db.commit()
                logger.error(
                    "background backfill deadline exceeded product_id=%s deadline_s=%s",
                    product_id,
                    BACKFILL_DEADLINE_SECONDS,
                )
    except Exception:  # noqa: BLE001
        logger.exception("deadline enforcer failed product_id=%s", product_id)


def run_backfill_in_background(product_id: int) -> None:
    """Background task: open a fresh session, run the full backfill, record status."""
    from datetime import UTC as _UTC, datetime as _dt
    from sqlalchemy.orm import Session as _Session

    from app.db import engine as _engine

    done_event = threading.Event()
    deadline_timer = threading.Timer(
        BACKFILL_DEADLINE_SECONDS, _deadline_enforcer, args=(product_id, done_event)
    )
    deadline_timer.daemon = True
    deadline_timer.start()

    with _Session(_engine) as db:
        product = db.get(TrackedProduct, product_id)
        if product is None:
            logger.warning("background backfill skipped: product_id=%s missing", product_id)
            done_event.set()
            deadline_timer.cancel()
            return
        try:
            result = backfill_product_timeline(db, product)
            # Re-fetch to avoid stale state and only update if deadline hasn't already failed it
            db.refresh(product)
            if product.backfill_status == "failed":
                logger.warning(
                    "background backfill finished after deadline enforcer flipped status product=%s",
                    product.slug,
                )
            else:
                product.backfill_status = "done"
                # Set informational backfill_error signalling empty-result paths
                if result.fetched_candidates == 0 and result.linked_news_count == 0:
                    product.backfill_error = "no_candidates: external sources returned nothing"
                elif result.linked_news_count == 0:
                    product.backfill_error = (
                        f"no_linked_news: found {result.fetched_candidates} candidates "
                        "but none matched product aliases"
                    )
                elif result.created_timeline_events == 0:
                    product.backfill_error = "no_timeline_events: LLM + fallback both returned empty"
                else:
                    product.backfill_error = None
                product.backfill_last_result = {
                    "fetched_candidates": result.fetched_candidates,
                    "linked_news_count": result.linked_news_count,
                    "created_timeline_events": result.created_timeline_events,
                    "finished_at": _dt.now(_UTC).isoformat(),
                }
                db.commit()
                logger.info(
                    "background backfill complete product=%s linked=%s events=%s",
                    product.slug,
                    result.linked_news_count,
                    result.created_timeline_events,
                )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            product = db.get(TrackedProduct, product_id)
            if product is not None:
                product.backfill_status = "failed"
                product.backfill_error = str(exc)[:500]
                db.commit()
            logger.exception("background backfill failed product_id=%s", product_id)
        finally:
            done_event.set()
            deadline_timer.cancel()
            try:
                db.rollback()
                product = db.get(TrackedProduct, product_id)
                if product is not None and product.backfill_status == "running":
                    product.backfill_status = "failed"
                    product.backfill_error = "unknown_error: run exited without setting terminal status"
                    db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("watchdog failed to finalize product_id=%s", product_id)


def slugify_product_name(value: str) -> str:
    lowered = value.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return normalized[:120] or "product"


def backfill_product_timeline(db: Session, product: TrackedProduct, glm5: GLM5Client | None = None) -> ProductBackfillResult:
    client = glm5 or GLM5Client()
    seed_terms = _product_search_terms(product)
    existing_candidates = search_news_candidates_for_product(db, seed_terms, limit=80)
    fetched_candidates = _fetch_external_candidates(product)
    enriched_fetched = enrich_items(fetched_candidates, glm5=client)
    inserted_count, updated_count, _ = upsert_news_items(db, enriched_fetched)
    logger.info(
        "product backfill persistence product=%s inserted=%s updated=%s fetched_candidates=%s",
        product.slug,
        inserted_count,
        updated_count,
        len(fetched_candidates),
    )

    all_candidates = search_news_candidates_for_product(db, seed_terms, limit=120)
    fetched_urls = {str(c.canonical_url) for c in fetched_candidates}
    if fetched_urls:
        from sqlalchemy import select as _select
        fetched_rows = db.scalars(
            _select(NewsItem).where(NewsItem.canonical_url.in_(fetched_urls))
        ).all()
        by_id = {item.id: item for item in all_candidates}
        for row in fetched_rows:
            by_id.setdefault(row.id, row)
        all_candidates = list(by_id.values())
    logger.info(
        "product backfill candidates assembled",
        extra={
            "product_slug": product.slug,
            "candidates_count": len(all_candidates),
            "existing_candidates": len(existing_candidates),
            "fetched_candidates": len(fetched_candidates),
        },
    )
    linked_count = _link_product_news(db, product, all_candidates, client, trusted_urls=fetched_urls)
    logger.info(
        "product backfill linking done",
        extra={
            "product_slug": product.slug,
            "linked_count": linked_count,
            "candidates_count": len(all_candidates),
        },
    )

    # Harvest authoritative aliases from CT.gov intervention metadata.
    try:
        new_aliases = harvest_ctgov_aliases(product)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "product backfill alias harvest failed product=%s error=%s",
            product.slug,
            exc,
        )
        new_aliases = []
    if new_aliases:
        existing_keys = {_alnum_key(a) for a in (product.aliases or []) if a}
        merged = list(product.aliases or [])
        appended: list[str] = []
        for alias in new_aliases:
            key = _alnum_key(alias)
            if key and key not in existing_keys:
                existing_keys.add(key)
                merged.append(alias)
                appended.append(alias)
        if appended:
            product.aliases = merged
            db.commit()
            db.refresh(product)
            logger.info(
                "product backfill aliases harvested",
                extra={
                    "product_slug": product.slug,
                    "new_aliases": appended,
                    "total_aliases": len(merged),
                },
            )
            # One extra linking pass with the expanded alias set so any
            # previously-unmatched news can now be linked.
            extended_terms = _product_search_terms(product)
            extended_candidates = search_news_candidates_for_product(
                db, extended_terms, limit=120
            )
            extra_linked = _link_product_news(
                db, product, extended_candidates, client, trusted_urls=fetched_urls
            )
            logger.info(
                "product backfill relink after alias expansion",
                extra={
                    "product_slug": product.slug,
                    "extra_linked": extra_linked,
                    "candidates_count": len(extended_candidates),
                },
            )
            linked_count = max(linked_count, extra_linked)

    timeline_events_count = _extract_timeline_events(db, product, client)
    logger.info(
        "product backfill timeline extraction done",
        extra={
            "product_slug": product.slug,
            "final_events_count": timeline_events_count,
            "linked_count": linked_count,
        },
    )
    mark_product_backfilled(db, product)
    return ProductBackfillResult(
        fetched_candidates=len(fetched_candidates),
        linked_news_count=linked_count,
        created_timeline_events=timeline_events_count,
    )


def _fetch_external_candidates(product: TrackedProduct) -> list[CandidateNewsItem]:
    queries = _build_external_queries(product)
    candidates: list[CandidateNewsItem] = []
    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for query in queries:
            # Per-source isolation: one dead source must not fail the whole backfill.
            for source_name, fetcher in (("pubmed", _fetch_pubmed), ("clinicaltrials", _fetch_clinicaltrials)):
                try:
                    source_items = fetcher(client, product, query)
                    candidates.extend(source_items)
                    logger.info(
                        "product external fetch ok",
                        extra={
                            "product_slug": product.slug,
                            "source": source_name,
                            "query": query,
                            "items": len(source_items),
                        },
                    )
                except (httpx.TimeoutException, httpx.HTTPError) as exc:
                    logger.warning(
                        "product external fetch http_error product=%s source=%s query=%s error=%s",
                        product.slug,
                        source_name,
                        query,
                        exc,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "product external fetch unexpected product=%s source=%s query=%s error=%s",
                        product.slug,
                        source_name,
                        query,
                        exc,
                    )
    deduped: dict[str, CandidateNewsItem] = {}
    for item in candidates:
        deduped[str(item.canonical_url)] = item
    return list(deduped.values())


def _fetch_pubmed(client: httpx.Client, product: TrackedProduct, query: str) -> list[CandidateNewsItem]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(MAX_RESULTS_PER_QUERY),
        "retmode": "json",
        "sort": "date",
    }
    try:
        response = client.get(PUBMED_ESEARCH_URL, params=params)
        response.raise_for_status()
        ids = (response.json().get("esearchresult") or {}).get("idlist") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("product pubmed esearch failed product=%s query=%s error=%s", product.slug, query, exc)
        return []
    if not ids:
        return []
    try:
        summary_response = client.get(
            PUBMED_ESUMMARY_URL,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        )
        summary_response.raise_for_status()
        result = summary_response.json().get("result") or {}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("product pubmed esummary failed product=%s query=%s error=%s", product.slug, query, exc)
        return []
    abstracts = _fetch_pubmed_abstracts(client, ids)
    items: list[CandidateNewsItem] = []
    for pmid in ids:
        record = result.get(pmid)
        if not record:
            continue
        title = clean_text(record.get("title"))
        if not title:
            continue
        link = PUBMED_ARTICLE_URL.format(pmid=pmid)
        published_at = _parse_pubmed_date(record.get("pubdate") or record.get("epubdate"))
        authors = ", ".join(
            a.get("name") for a in (record.get("authors") or [])[:4] if a.get("name")
        )
        source = clean_text(record.get("source")) or "PubMed"
        summary_parts = [part for part in [authors, source, record.get("pubdate")] if part]
        summary = " · ".join(summary_parts)
        abstract = abstracts.get(pmid, "")
        content_parts = [part for part in [summary, abstract] if part]
        content_text = "\n\n".join(content_parts) or title
        items.append(
            CandidateNewsItem(
                title=title,
                canonical_url=canonicalize_url(link),
                source_name="PubMed",
                published_at=published_at,
                content_text=content_text,
                raw_summary=summary,
                language="en",
            )
        )
    return items


def _fetch_pubmed_abstracts(client: httpx.Client, pmids: list[str]) -> dict[str, str]:
    if not pmids:
        return {}
    try:
        response = client.get(
            PUBMED_EFETCH_URL,
            params={"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("product pubmed efetch failed ids=%s error=%s", pmids, exc)
        return {}
    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.warning("product pubmed efetch parse failed error=%s", exc)
        return {}
    out: dict[str, str] = {}
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        texts = [
            (seg.text or "").strip()
            for seg in article.iter("AbstractText")
            if (seg.text or "").strip()
        ]
        if texts:
            out[pmid_el.text.strip()] = "\n".join(texts)
    return out


def _fetch_clinicaltrials(client: httpx.Client, product: TrackedProduct, query: str) -> list[CandidateNewsItem]:
    params = {
        "query.term": query,
        "pageSize": str(MAX_RESULTS_PER_QUERY),
        "format": "json",
    }
    try:
        response = client.get(CLINICALTRIALS_SEARCH_URL, params=params)
        response.raise_for_status()
        studies = response.json().get("studies") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "product clinicaltrials fetch failed product=%s query=%s error=%s", product.slug, query, exc
        )
        return []
    items: list[CandidateNewsItem] = []
    for study in studies:
        protocol = study.get("protocolSection") or {}
        ident = protocol.get("identificationModule") or {}
        nct_id = ident.get("nctId")
        brief_title = clean_text(ident.get("briefTitle"))
        if not nct_id or not brief_title:
            continue
        status_module = protocol.get("statusModule") or {}
        last_update = (status_module.get("lastUpdatePostDateStruct") or {}).get("date") \
            or (status_module.get("startDateStruct") or {}).get("date")
        overall_status = clean_text(status_module.get("overallStatus")) or ""
        phase_list = (protocol.get("designModule") or {}).get("phases") or []
        phase_str = ", ".join(phase_list) if phase_list else ""
        conditions = ", ".join((protocol.get("conditionsModule") or {}).get("conditions") or [])
        sponsor = clean_text(
            ((protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name")
        ) or ""
        interventions_mod = protocol.get("armsInterventionsModule") or {}
        intervention_bits: list[str] = []
        for intervention in interventions_mod.get("interventions") or []:
            name = clean_text(intervention.get("name"))
            itype = clean_text(intervention.get("type"))
            if name and itype:
                intervention_bits.append(f"{itype}: {name}")
            elif name:
                intervention_bits.append(name)
            other_names = intervention.get("otherNames") or []
            intervention_bits.extend(clean_text(n) for n in other_names if n)
        interventions = "; ".join(bit for bit in intervention_bits if bit)
        brief_summary = clean_text(
            (protocol.get("descriptionModule") or {}).get("briefSummary")
        ) or ""
        summary_bits = [
            f"{nct_id}",
            overall_status,
            phase_str,
            conditions,
            sponsor,
            f"Interventions: {interventions}" if interventions else "",
        ]
        summary = " · ".join(bit for bit in summary_bits if bit)
        content_text = "\n\n".join(part for part in [summary, brief_summary] if part)
        title = f"[{nct_id}] {brief_title}"
        link = CLINICALTRIALS_STUDY_URL.format(nct_id=nct_id)
        published_at = _parse_iso_date(last_update)
        items.append(
            CandidateNewsItem(
                title=title,
                canonical_url=canonicalize_url(link),
                source_name="ClinicalTrials.gov",
                published_at=published_at,
                content_text=content_text or brief_title,
                raw_summary=summary,
                language="en",
            )
        )
    return items


# Generic terms we never want to harvest as drug aliases.
_ALIAS_BLOCKLIST = {
    "placebo",
    "standard of care",
    "best supportive care",
    "no intervention",
    "control",
    "sham",
    "saline",
    "vehicle",
    "matching placebo",
    "usual care",
    "observation",
    "none",
    "n/a",
    "not applicable",
    "active comparator",
}

# Lymphodepletion / preconditioning agents and common clinical-trial add-ons
# that frequently appear alongside the tracked investigational product but are
# not the product itself. Matched case-insensitively AND substring-wise against
# an intervention name (e.g. "Bupivacaine Collagen Sponge" is blocked because
# it contains "bupivacaine").
_LYMPHODEPLETION_AND_CLINICAL_NOISE = {
    # lymphodepletion / preconditioning chemo
    "cyclophosphamide",
    "fludarabine",
    "bendamustine",
    "cytarabine",
    "mesna",
    # local anesthetics
    "bupivacaine",
    "lidocaine",
    "ropivacaine",
    # steroids / CRS management
    "dexamethasone",
    "methylprednisolone",
    "hydrocortisone",
    "prednisone",
    "tocilizumab",
    # OTC / supportive
    "acetaminophen",
    "paracetamol",
    "diphenhydramine",
    # vehicles / comparators
    "saline",
    "normal saline",
    "placebo",
    "best supportive care",
    "standard of care",
    "vehicle",
    "sham",
    # delivery matrices / diluents
    "collagen sponge",
    "collagen implant",
    "sterile water",
    "d5w",
    "lactated ringer",
}

# Drug-code heuristic: e.g. CB-010, JCAR017, AZD-0120, KTE-C19, CTL019.
_DRUG_CODE_RE = re.compile(r"^[A-Z]{1,6}-?\d{2,6}[A-Z]?(?:-[A-Z0-9]{1,4})?$")
# INN stem suffixes that virtually guarantee a biologic drug name.
_DRUG_STEM_SUFFIXES = ("-cel", "-mab", "-gene", "cel", "mab", "gene", "leucel", "vec")


def _is_blocked_noise(value: str, *, tracked_product_key: str | None = None) -> bool:
    """Return True if the intervention name is clinical-trial noise.

    Substring match against ``_LYMPHODEPLETION_AND_CLINICAL_NOISE`` (case
    insensitive). Exempts the tracked product's own display_name by alnum key.
    """
    if not value:
        return True
    folded = value.casefold()
    if tracked_product_key and _alnum_key(value) == tracked_product_key:
        return False
    for term in _LYMPHODEPLETION_AND_CLINICAL_NOISE:
        if term in folded:
            return True
    return False


def _is_drug_code_like(alias: str) -> bool:
    """Heuristic for 'drug-code-like' aliases worth querying CT.gov with."""
    if not alias:
        return False
    cleaned = alias.strip()
    if not cleaned:
        return False
    # Strip a leading '-' only; keep intra-token hyphens.
    compact = cleaned.replace(" ", "")
    if _DRUG_CODE_RE.match(compact):
        return True
    low = cleaned.casefold()
    if any(low.endswith(suf) for suf in _DRUG_STEM_SUFFIXES):
        return True
    return False


def _looks_like_drug_identifier(value: str) -> bool:
    """Filter that excludes obvious non-drug intervention names."""
    if not value:
        return False
    cleaned = value.strip()
    if len(cleaned) < 2 or len(cleaned) > 120:
        return False
    if cleaned.casefold() in _ALIAS_BLOCKLIST:
        return False
    # Must contain at least one alphanumeric character.
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return False
    return True


def _extract_intervention_aliases_from_studies(
    studies: list[dict],
    *,
    query_alnum_keys: set[str] | None = None,
    tracked_product_key: str | None = None,
) -> list[str]:
    """Pull intervention name + otherNames from a CT.gov v2 studies payload.

    When ``query_alnum_keys`` is supplied, only extract aliases from
    interventions whose ``name`` or any ``otherNames`` alnum-matches one of the
    query aliases — avoiding bleed-over of co-administered drugs from the same
    study.
    """
    found: list[str] = []
    for study in studies or []:
        try:
            protocol = study.get("protocolSection") or {}
            interventions_mod = protocol.get("armsInterventionsModule") or {}
            for intervention in interventions_mod.get("interventions") or []:
                name = clean_text(intervention.get("name"))
                other_names = [clean_text(o) for o in (intervention.get("otherNames") or [])]
                other_names = [o for o in other_names if o]

                # Optional per-intervention relevance filter.
                if query_alnum_keys is not None:
                    intervention_keys = {
                        _alnum_key(n) for n in ([name] + other_names) if n
                    }
                    intervention_keys.discard("")
                    if not (intervention_keys & query_alnum_keys):
                        continue

                if (
                    name
                    and _looks_like_drug_identifier(name)
                    and not _is_blocked_noise(name, tracked_product_key=tracked_product_key)
                ):
                    found.append(name)
                for other_clean in other_names:
                    if (
                        _looks_like_drug_identifier(other_clean)
                        and not _is_blocked_noise(
                            other_clean, tracked_product_key=tracked_product_key
                        )
                    ):
                        found.append(other_clean)
        except (AttributeError, TypeError):
            continue
    return found


def harvest_ctgov_aliases(product: TrackedProduct) -> list[str]:
    """Query CT.gov for the product's existing aliases and return new alias candidates.

    Only queries CT.gov by drug-code-like existing aliases (the product's
    display_name plus any drug-code-like alias) — NEVER by company name alone,
    to avoid dragging in co-administered drugs from unrelated sponsor studies.
    Uses CT.gov v2's ``query.intr`` (intervention-field) param so matches come
    from actual intervention names. Post-fetch, only extracts aliases from
    interventions that alnum-match one of the query aliases.

    Returns a deduplicated (by alnum key) list of aliases that are NOT already
    in the product's alias set, capped at 10 entries. Defensive: any
    network/parse failure yields [].
    """
    # Assemble candidate query aliases: display_name + any alias that looks
    # drug-code-like. Explicitly exclude company name.
    candidate_aliases: list[str] = []
    if product.display_name:
        candidate_aliases.append(product.display_name)
    for alias in product.aliases or []:
        if alias and _is_drug_code_like(alias):
            candidate_aliases.append(alias)

    # Drop company-name matches, dedupe by casefold.
    company_cf = (product.company_name or "").casefold().strip()
    seen_q: set[str] = set()
    queries: list[str] = []
    for alias in candidate_aliases:
        cf = alias.casefold().strip()
        if not cf or cf == company_cf or cf in seen_q:
            continue
        # Require drug-code-like OR is the canonical display_name.
        if alias != product.display_name and not _is_drug_code_like(alias):
            continue
        seen_q.add(cf)
        queries.append(alias)
    queries = queries[:MAX_QUERY_COUNT]
    if not queries:
        return []

    query_alnum_keys = {_alnum_key(q) for q in queries}
    query_alnum_keys.discard("")

    existing_keys = {_alnum_key(a) for a in (product.aliases or []) if a}
    existing_keys.add(_alnum_key(product.display_name))
    tracked_product_key = _alnum_key(product.display_name)
    seen_keys: set[str] = set()
    new_aliases: list[str] = []
    try:
        with httpx.Client(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            for query in queries:
                try:
                    response = client.get(
                        CLINICALTRIALS_SEARCH_URL,
                        params={
                            # CT.gov v2 intervention-field query — restricts
                            # matches to the protocolSection.armsInterventions
                            # Module.interventions name/otherNames field.
                            "query.intr": query,
                            "pageSize": str(MAX_RESULTS_PER_QUERY),
                            "format": "json",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "harvest_ctgov_aliases fetch failed product=%s query=%s error=%s",
                        product.slug,
                        query,
                        exc,
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "harvest_ctgov_aliases unexpected product=%s query=%s error=%s",
                        product.slug,
                        query,
                        exc,
                    )
                    continue
                studies = payload.get("studies") if isinstance(payload, dict) else None
                if not isinstance(studies, list):
                    continue
                for candidate in _extract_intervention_aliases_from_studies(
                    studies,
                    query_alnum_keys=query_alnum_keys,
                    tracked_product_key=tracked_product_key,
                ):
                    key = _alnum_key(candidate)
                    if not key or key in existing_keys or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    new_aliases.append(candidate)
                    if len(new_aliases) >= 10:
                        return new_aliases
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "harvest_ctgov_aliases outer failure product=%s error=%s",
            product.slug,
            exc,
        )
        return []
    return new_aliases


def _parse_pubmed_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    for fmt in ("%Y %b %d", "%Y %b", "%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _parse_iso_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _link_product_news(
    db: Session,
    product: TrackedProduct,
    items: list[NewsItem],
    glm5: GLM5Client,
    *,
    trusted_urls: set[str] | None = None,
) -> int:
    trusted = trusted_urls or set()
    linked_count = 0
    for item in items:
        match = _match_news_to_product(product, item, glm5)
        if not match.is_relevant and item.canonical_url in trusted:
            match = ProductNewsMatch(
                is_relevant=True,
                matched_alias=None,
                matched_company=None,
                confidence=0.4,
                reason_short="Fetched via product-specific source query.",
            )
            match_source = "source_query"
        else:
            match_source = "glm5" if match.confidence < 0.95 else "keyword"
        if not match.is_relevant:
            continue
        upsert_product_news_link(
            db,
            product_id=product.id,
            news_item_id=item.id,
            match_source=match_source,
            match_confidence=match.confidence,
        )
        linked_count += 1
    db.commit()
    return linked_count


def _extract_timeline_events(db: Session, product: TrackedProduct, glm5: GLM5Client) -> int:
    linked_news = list_linked_news_for_product(db, product.id)
    logger.info(
        "product timeline extraction starting",
        extra={
            "product_slug": product.slug,
            "linked_count": len(linked_news),
        },
    )
    event_count = 0
    glm5_extraction_count = 0
    fallback_events_count = 0
    import time as _time
    for item in linked_news:
        _t0 = _time.monotonic()
        try:
            extraction = glm5.extract_product_timeline(
                product_name=product.display_name,
                company_name=product.company_name,
                aliases=product.aliases or [],
                indications=product.indications or [],
                title=item.title,
                content_text=item.content_text or item.short_summary or item.title,
            )
            logger.info(
                "product timeline glm5 extraction item done",
                extra={
                    "product_slug": product.slug,
                    "news_item_id": item.id,
                    "duration_s": round(_time.monotonic() - _t0, 2),
                    "events": len(extraction.events) if extraction else 0,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "product timeline glm5 extraction failed product=%s news_item_id=%s error=%s",
                product.slug,
                item.id,
                exc,
            )
            extraction = None
        if extraction is not None and extraction.events:
            events = extraction.events
            glm5_extraction_count += len(events)
        else:
            events = _fallback_timeline_events(product, item)
            fallback_events_count += len(events)
        for event in events:
            try:
                event_dt = _draft_date_to_datetime(event.event_date, event.event_date_precision)
            except ValueError:
                logger.warning(
                    "product timeline draft date parse failed product=%s news_item_id=%s event_date=%s precision=%s",
                    product.slug,
                    item.id,
                    event.event_date,
                    event.event_date_precision,
                )
                continue
            event_hash = _event_hash(product.id, event, item.canonical_url)
            upsert_product_timeline_event(
                db,
                product_id=product.id,
                event_date=event_dt,
                event_date_precision=event.event_date_precision,
                milestone_type=event.milestone_type,
                milestone_label=event.milestone_label,
                phase_label=event.phase_label,
                headline=event.headline,
                event_summary=event.event_summary,
                indication=event.indication,
                region=event.region,
                confidence=event.confidence,
                evidence_news_item_ids=[item.id],
                evidence_urls=[item.canonical_url],
                event_hash=event_hash,
            )
            event_count += 1
    db.commit()
    logger.info(
        "product timeline extraction finished",
        extra={
            "product_slug": product.slug,
            "linked_count": len(linked_news),
            "glm5_extraction_count": glm5_extraction_count,
            "fallback_events_count": fallback_events_count,
            "final_events_count": event_count,
        },
    )
    return event_count


def _product_search_terms(product: TrackedProduct) -> list[str]:
    terms = [product.display_name]
    if product.company_name:
        terms.append(product.company_name)
    terms.extend(product.aliases or [])
    terms.extend(product.indications or [])
    seen = set()
    ordered = []
    for term in terms:
        normalized = normalize_title(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(term)
    return ordered


def _build_external_queries(product: TrackedProduct) -> list[str]:
    queries: list[str] = [product.display_name]
    if product.company_name:
        queries.append(f"{product.display_name} {product.company_name}")
    for alias in (product.aliases or [])[:2]:
        if alias and alias.casefold() != product.display_name.casefold():
            queries.append(alias)
    # dedupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(q)
    return unique[:MAX_QUERY_COUNT]


def _alnum_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _match_news_to_product(product: TrackedProduct, item: NewsItem, glm5: GLM5Client) -> ProductNewsMatch:
    raw_haystack = " ".join(filter(None, [item.title, item.short_summary, item.content_text]))
    haystack = normalize_title(raw_haystack)
    alnum_haystack = _alnum_key(raw_haystack)
    terms = _product_search_terms(product)

    def term_in_haystack(term: str) -> bool:
        n = normalize_title(term)
        if n and n in haystack:
            return True
        a = _alnum_key(term)
        return bool(a) and len(a) >= 3 and a in alnum_haystack

    matched_alias = next((term for term in terms if term_in_haystack(term)), None)
    matched_company = (
        product.company_name
        if product.company_name and term_in_haystack(product.company_name)
        else None
    )
    if matched_alias and (matched_company or matched_alias.casefold() == product.display_name.casefold()):
        return ProductNewsMatch(
            is_relevant=True,
            matched_alias=matched_alias,
            matched_company=matched_company,
            confidence=0.98,
            reason_short="Direct alias/company match.",
        )
    if matched_alias:
        return ProductNewsMatch(
            is_relevant=True,
            matched_alias=matched_alias,
            matched_company=matched_company,
            confidence=0.9,
            reason_short="Direct alias match.",
        )
    llm_match = glm5.match_product_news(
        product_name=product.display_name,
        company_name=product.company_name,
        aliases=product.aliases or [],
        indications=product.indications or [],
        title=item.title,
        content_text=item.content_text or item.short_summary or item.title,
    )
    if llm_match is not None:
        return llm_match
    return ProductNewsMatch(
        is_relevant=False,
        matched_alias=None,
        matched_company=None,
        confidence=0.0,
        reason_short="No deterministic or model match.",
    )


def _fallback_timeline_events(product: TrackedProduct, item: NewsItem) -> list[ProductTimelineEventDraft]:
    haystack = f"{item.title} {item.short_summary} {item.content_text or ''}".casefold()
    events: list[ProductTimelineEventDraft] = []
    mappings = [
        ("ind_cta_iit", "IND / CTA / IIT milestone", (" ind ", "ind ", "cta", "iit")),
        ("phase_start", "Clinical phase started", ("phase 1", "phase i", "phase 2", "phase ii", "phase 3", "phase iii", "trial initiation")),
        ("phase_result", "Clinical result reported", ("topline", "interim", "results", "met primary endpoint")),
        ("preclinical", "Preclinical / research update", ("preclinical", "research", "proof-of-concept")),
        ("regulatory", "Regulatory update", ("approval", "approved", "fda", "ema", "clearance")),
        ("partnering", "Partnership / licensing update", ("partnership", "collaboration", "license")),
        ("financing", "Financing update", ("financing", "funding", "series ")),
        ("setback", "Setback / hold", ("hold", "crl", "rejected", "terminated")),
    ]
    for milestone_type, label, keywords in mappings:
        if any(keyword in haystack for keyword in keywords):
            phase_label = _phase_label(haystack)
            events.append(
                ProductTimelineEventDraft(
                    event_date=item.published_at.date().isoformat(),
                    event_date_precision="day",
                    milestone_type=milestone_type,
                    milestone_label=label,
                    phase_label=phase_label,
                    headline=item.title,
                    event_summary=item.short_summary,
                    indication=(product.indications or [None])[0],
                    region=None,
                    confidence=0.55,
                    evidence_quote_short=None,
                )
            )
            break
    return events


def _phase_label(haystack: str) -> str | None:
    if "phase 3" in haystack or "phase iii" in haystack:
        return "Phase 3"
    if "phase 2" in haystack or "phase ii" in haystack:
        return "Phase 2"
    if "phase 1" in haystack or "phase i" in haystack:
        return "Phase 1"
    if "ind" in haystack or "cta" in haystack or "iit" in haystack:
        return "IND / CTA / IIT"
    if "preclinical" in haystack or "research" in haystack:
        return "Preclinical"
    return None


def _draft_date_to_datetime(value: str, precision: str) -> datetime:
    try:
        if precision == "year":
            return datetime(int(value), 1, 1, tzinfo=UTC)
        if precision == "month":
            year, month = value.split("-", 1)
            return datetime(int(year), int(month), 1, tzinfo=UTC)
        year, month, day = value.split("-", 2)
        return datetime(int(year), int(month), int(day), tzinfo=UTC)
    except Exception as exc:
        raise ValueError(f"invalid draft date {value!r} for precision {precision!r}") from exc


def _entry_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


def _event_hash(product_id: int, event: ProductTimelineEventDraft, evidence_url: str) -> str:
    digest = hashlib.sha256(
        f"{product_id}|{event.event_date}|{event.milestone_type}|{event.phase_label or ''}|{event.indication or ''}|{evidence_url}".encode(
            "utf-8"
        )
    ).hexdigest()
    return digest
