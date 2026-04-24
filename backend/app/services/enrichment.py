import logging
import re
from hashlib import sha256

from app.schemas.pipeline import CandidateNewsItem, ClassifiedNewsItem
from app.services.classification import classify_with_rules, validate_category
from app.services.glm5_client import GLM5Client

logger = logging.getLogger(__name__)

# Minimum relevance_to_cell_therapy required to keep the item's original
# category. Below this, the item is demoted to "Other" so it does not
# pollute the cell-therapy-focused views while remaining searchable.
CELL_THERAPY_RELEVANCE_THRESHOLD = 0.7


def title_hash(title: str) -> str:
    return sha256(normalize_title(title).encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    lowered = title.casefold()
    without_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(without_punctuation.split())


def fallback_summary(item: CandidateNewsItem) -> str:
    text = item.raw_summary or item.content_text or item.title
    normalized = " ".join(text.split())
    if len(normalized) <= 320:
        return normalized
    return f"{normalized[:317].rstrip()}..."


# Strong cell-therapy-specific terms — any match pushes relevance above the
# persistence threshold. Kept broad enough to catch CGT pipeline companies,
# manufacturing (viral vector, cryopreservation), and regulatory milestones
# for cell-therapy programs even when the drug is not named.
CELL_THERAPY_STRONG_TERMS: tuple[str, ...] = (
    # CAR / engineered T cells
    "car-t", "car t", "cart", "car-nk", "car nk", "car-m", "car m",
    "tcr-t", "tcr t", "til therapy", "til ", "bcma car", "cd19 car",
    "engineered t cell", "engineered t-cell", "armored car", "universal car",
    "in vivo car", "allogeneic car", "autologous car",
    # Gene-edited / vector-based cell therapies
    "gene-edited t cell", "gene edited t cell", "crispr t cell",
    "base-edited t cell", "base edited t cell", "lentiviral vector t cell",
    # Stem cell / regenerative
    "ipsc therapy", "ipsc-derived", "ipsc derived", "induced pluripotent",
    "pluripotent stem", "mesenchymal stem cell", " msc ", "msc therapy",
    "hematopoietic stem cell", "hsc transplant", "stem cell therapy",
    # Other cell therapies
    "regulatory t cell therapy", "treg therapy", "nk cell therapy",
    "dendritic cell vaccine", "adoptive cell transfer", " act therapy",
    # Umbrella terms
    "cell therapy", "cell & gene therapy", "cell and gene therapy",
    " cgt ", "cgt pipeline", "regenerative medicine",
    "allogeneic", "autologous",
    # Chinese
    "细胞治疗", "细胞疗法", "干细胞", "免疫细胞", "基因编辑细胞",
    "通用型car", "自体", "异体", "诱导多能干细胞", "ipsc",
)

# Supporting / context terms — CGT-adjacent manufacturing, modality hints.
CELL_THERAPY_CONTEXT_TERMS: tuple[str, ...] = (
    "viral vector", "lentiviral", "aav vector", "cryopreservation",
    "fill-finish", "cdmo", "cgmp", "t cell", "t-cell", "nk cell",
    "gene therapy", "cell line", "leukapheresis", "apheresis",
)

# Penalty terms — modalities that are NOT cell therapy. If only these match
# and no strong cell-therapy term matches, we downgrade relevance.
NON_CELL_MODALITY_TERMS: tuple[str, ...] = (
    "small molecule", "small-molecule", "oral pill", "oral tablet",
    "antibody-drug conjugate", "adc ", " adc,", "bispecific antibody",
    "monoclonal antibody", "sirna", "antisense oligonucleotide",
    "aso ", "peptide drug", "vaccine adjuvant",
    # Expanded exclusions — modalities/topics routinely misclassified as CGT.
    "psychedelic", "psychedelics", "psilocybin", "mdma therapy", "mdma",
    "kinase inhibitor", "cdk inhibitor", "cdk4", "cdk6", "cdk7", "cdk 4/6",
    "dermatology", "aesthetic medicine", "laser aesthetic", "cosmeceutical",
    "alopecia", "hair regrowth", "hair-regrowth",
    "cleanroom", "clean-room", "industry award", "conference preview",
    "m&a rumor", "generic drug", "biosimilar",
)


def fallback_importance(item: CandidateNewsItem, category: str) -> float:
    base = 0.45
    if category in {"Clinical/Regulatory Progress", "Financing", "Partnership/Licensing"}:
        base += 0.15
    haystack = item.title.casefold()
    if any(term in haystack for term in CELL_THERAPY_STRONG_TERMS):
        base += 0.15
    return min(base, 0.95)


def fallback_relevance(item: CandidateNewsItem) -> float:
    haystack = f"{item.title} {item.content_text or ''} {item.raw_summary or ''}".casefold()
    strong_hit = any(term in haystack for term in CELL_THERAPY_STRONG_TERMS)
    context_hit = any(term in haystack for term in CELL_THERAPY_CONTEXT_TERMS)
    non_cell_hit = any(term in haystack for term in NON_CELL_MODALITY_TERMS)

    # Hard override: any NON_CELL term with no strong CGT term => force <= 0.2
    # to guarantee the relevance gate demotes the item regardless of other heuristics.
    if non_cell_hit and not strong_hit:
        return 0.1

    if strong_hit:
        # Strong CGT signal — even if non-cell terms appear (comparison piece).
        return 0.85 if non_cell_hit else 0.9
    if context_hit and not non_cell_hit:
        # Manufacturing / adjacent without explicit non-cell modality.
        return 0.55
    if non_cell_hit:
        # Purely non-cell modality news — keep very low to exclude.
        return 0.1
    if any(term in haystack for term in ("biotech", "biopharma", "clinical", "therapeutic")):
        return 0.25
    return 0.15


def enrich_items(items: list[CandidateNewsItem], glm5: GLM5Client | None = None) -> list[ClassifiedNewsItem]:
    client = glm5 or GLM5Client()
    enriched: list[ClassifiedNewsItem] = []
    rule_only_count = 0
    model_count = 0
    fallback_count = 0
    for item in items:
        category, ambiguous = classify_with_rules(item)
        model_enrichment = None
        if ambiguous and client.is_configured:
            model_enrichment = client.enrich_item(
                title=item.title,
                content_text=item.content_text or item.raw_summary or item.title,
                category_hint=category,
            )

        if model_enrichment is not None:
            category = validate_category(model_enrichment.category)
            short_summary = model_enrichment.one_line_summary
            entities = model_enrichment.entities
            importance_score = model_enrichment.importance_score
            relevance_to_cell_therapy = model_enrichment.relevance_to_cell_therapy
            model_count += 1
        else:
            short_summary = fallback_summary(item)
            entities = None
            importance_score = fallback_importance(item, category)
            relevance_to_cell_therapy = fallback_relevance(item)
            if ambiguous:
                logger.info("classification fallback used for ambiguous item: %s", item.title)
                fallback_count += 1
            else:
                rule_only_count += 1

        # Relevance gate: demote low-CGT-relevance items to "Other" so they
        # still exist for general biomedical search but do not surface in
        # cell-therapy-focused listings. Preserves Manufacturing/CMC and
        # Clinical/Regulatory Progress ONLY when CGT signal is present.
        if (
            relevance_to_cell_therapy is not None
            and relevance_to_cell_therapy < CELL_THERAPY_RELEVANCE_THRESHOLD
            and category != "Other"
        ):
            logger.info(
                "relevance gate demoting item category=%s relevance=%.2f title=%s",
                category,
                relevance_to_cell_therapy,
                item.title[:120],
            )
            category = "Other"

        # Corporate-dynamics tagging (APPEND-ONLY; does not affect thresholds
        # or modality terms). Matches a curated cell-therapy company list and
        # detects layoffs / new-pipeline / financing signals from the item
        # text. See app.services.corporate_dynamics.
        from app.services.corporate_dynamics import (
            detect_corporate_signals,
            match_company,
        )
        _corp_text = " ".join(
            filter(None, [item.title, item.content_text, item.raw_summary])
        )
        _company_name = match_company(_corp_text)
        _signals = detect_corporate_signals(_corp_text) or None

        try:
            enriched.append(
                ClassifiedNewsItem(
                    **item.model_dump(),
                    title_hash=title_hash(item.title),
                    category=category,
                    short_summary=short_summary,
                    entities=entities,
                    importance_score=importance_score,
                    relevance_to_cell_therapy=relevance_to_cell_therapy,
                    company_name=_company_name,
                    corporate_signals=_signals,
                )
            )
        except Exception:
            logger.exception("classification/enrichment validation failure: %s", item.title)
    logger.info(
        "classification/enrichment paths rule_only=%s model=%s ambiguous_fallback=%s",
        rule_only_count,
        model_count,
        fallback_count,
    )
    return enriched
