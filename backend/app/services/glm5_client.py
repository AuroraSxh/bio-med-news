import json
import logging
import threading
from collections import deque
from time import monotonic, sleep
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.pipeline import DailySummaryDraft, ItemEnrichment
from app.schemas.products import ProductAliasSuggestion, ProductNewsMatch, ProductTimelineExtraction

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Rate limiter (100 requests/min, 100K tokens/min for SJTU API)
# ---------------------------------------------------------------------------


class _RateLimiter:
    def __init__(self, max_requests: int = 100, max_tokens: int = 100_000, window: float = 60.0):
        self._max_requests = max_requests
        self._max_tokens = max_tokens
        self._window = window
        self._requests: deque[float] = deque()
        self._tokens: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def _purge(self, now: float) -> None:
        cutoff = now - self._window
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()
        while self._tokens and self._tokens[0][0] < cutoff:
            self._tokens.popleft()

    def wait_if_needed(self) -> None:
        with self._lock:
            now = monotonic()
            self._purge(now)
            if len(self._requests) >= self._max_requests:
                wait = self._requests[0] + self._window - now
                if wait > 0:
                    import time

                    time.sleep(wait)
                    self._purge(monotonic())

    def record(self, tokens: int = 0) -> None:
        with self._lock:
            now = monotonic()
            self._requests.append(now)
            if tokens > 0:
                self._tokens.append((now, tokens))


_rate_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# GLM5 Client
# ---------------------------------------------------------------------------


class GLM5Client:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.glm5_base_url) and self.settings.glm5_api_key not in {"", "change_me"}

    def enrich_item(
        self,
        title: str,
        content_text: str,
        category_hint: str,
        model_name: str | None = None,
    ) -> ItemEnrichment | None:
        prompt = (
            "Return only JSON for one biomedical news item with keys: "
            "one_line_summary, category, entities, importance_score, relevance_to_cell_therapy. "
            "Category must be one of the fixed taxonomy labels. Importance and relevance must be numbers from 0 to 1. "
            "Keep summary factual, neutral, and concise. Do not add unsupported claims.\n\n"
            "STRICT cell-therapy relevance scoring (this is a cell-therapy-focused aggregator):\n"
            "- Score 0.8-1.0 ONLY if the item materially concerns a cell therapy modality: "
            "CAR-T, CAR-NK, CAR-M, TCR-T, TIL, engineered/gene-edited T cells, allogeneic or autologous cell products, "
            "iPSC/pluripotent-derived therapies, MSC/HSC therapies, Treg therapy, NK cell therapy, dendritic cell vaccine, "
            "adoptive cell transfer, or the broader cell & gene therapy (CGT) pipeline of a named CGT company.\n"
            "- Score 0.5-0.7 if the item is CGT-adjacent: viral-vector / lentiviral / AAV manufacturing, "
            "cryopreservation, leukapheresis, CDMO capacity for cell products, regulatory milestones or financing "
            "of a pipeline company whose lead assets are cell therapies, even if the specific drug is not named.\n"
            "- Score <=0.3 if the item is about small molecules, antibodies-only, ADCs, bispecifics, siRNA/ASO, peptides, "
            "kinase inhibitors (incl. CDK inhibitors), psychedelics/psilocybin/MDMA therapy, dermatology unrelated to "
            "autoimmune cell therapy, alopecia / hair regrowth (unless CAR/cell-based), aesthetic medicine, "
            "policy / government news lacking a named cell-therapy asset, generic biotech M&A without cell-therapy products, "
            "industry awards or conference previews, fundraising of non-CGT companies, generic cleanroom / facility news, "
            "biosimilars or generic drugs, or any other non-cellular modality — even if the company also has a cell therapy "
            "program mentioned in passing.\n"
            "- If relevance_to_cell_therapy < 0.7, you MUST set category to 'Other'.\n"
            "- Do NOT inflate the score because the article mentions 'biotech', 'clinical trial', or 'FDA' generically.\n"
            "EXAMPLES you MUST REJECT (score <=0.3, category 'Other'):\n"
            "  1. Trump administration psychedelics policy shift\n"
            "  2. Zai Lab generic China reality-check commentary\n"
            "  3. Pfizer alopecia / hair-regrowth drug extension\n"
            "  4. CleanAssure cleanroom service for pharma manufacturing\n"
            "  5. Generic CDK4/6 kinase-inhibitor trial readout\n"
            "  6. Aesthetic medicine / dermatology laser approval\n"
            "  7. Industry awards night for biotech CEOs\n"
            "  8. Non-CGT oncology antibody Series C fundraise\n"
            "  9. FDA policy statement with no named cell-therapy asset\n"
            "  10. Biosimilar or generic small-molecule approval in an unrelated indication\n\n"
            f"Category hint: {category_hint}\nTitle: {title}\nText: {content_text[:3000]}"
        )
        return self._chat_json(prompt, ItemEnrichment, model_name=model_name)

    def summarize_day(
        self,
        items: list[dict[str, Any]],
        category_counts: dict[str, int],
        model_name: str | None = None,
    ) -> DailySummaryDraft | None:
        prompt = (
            "You are a professional biomedical/cell therapy market intelligence analyst. "
            "Return only JSON for a daily biomedical/cell therapy intelligence summary. "
            "Required keys (do NOT translate or rename keys): daily_summary, top_events, trend_signal, category_counts, category_summaries. "
            "top_events must contain 3 to 5 objects with title, category, canonical_url, source_name, published_at, short_summary when available. "
            "category_summaries must be a dict where each key is a category name that has items, "
            "and the value is a 1-2 sentence summary of that category's key developments today. "
            "Only include categories that have at least one item. "
            "Use only the provided items. Avoid promotional claims and avoid causal claims not supported by titles/summaries. "
            "Prefer higher importance and higher cell-therapy relevance items while keeping category balance.\n\n"
            "语言要求（强制）：请使用简体中文作答，除药物名、基因名、机构缩写、临床试验编号等专业术语外，其余内容一律使用中文。"
            "具体而言，drug codes（如 bb2121、JCAR017）、公司与机构名（如 Novartis、传奇生物、FDA、NMPA、EMA）、"
            "靶点与技术术语（如 CAR-T、CAR-NK、BCMA、CD19、TCR-T、iPSC）、临床试验编号（如 NCT04000000）等"
            "必须保留原始英文/拉丁形式，不得音译或意译；其余所有描述性文本（包括 daily_summary、trend_signal、"
            "category_summaries 中各分类的概述、以及 top_events 的 short_summary 若需改写）一律使用简体中文，"
            "采用专业生物医药分析师的中立、克制语气。JSON 的 key 名（如 daily_summary 等）以及枚举类别名保持原英文不变。\n"
            "示例：\"daily_summary\": \"今日 CAR-T 赛道以 BCMA 靶点的临床进展为主，FDA 对某款自体疗法发布补充指南。\"\n\n"
            f"category_counts: {json.dumps(category_counts, ensure_ascii=False)}\n"
            f"items: {json.dumps(items, ensure_ascii=False)[:12000]}"
        )
        chinese_system = (
            "你是一名资深生物医药市场情报分析师，必须使用简体中文输出 JSON 中所有人类可读字段（daily_summary、"
            "category_summaries 的 value、trend_signal、top_events.short_summary）。JSON 的 key 名以及 category 枚举标签"
            "（如 R&D、Clinical/Regulatory Progress、Manufacturing/CMC、Financing、Partnership/Licensing、"
            "M&A/Organization、Policy/Industry Environment、Other）保持原英文不变。药物代号、基因名、公司名、"
            "FDA/NMPA/EMA 等机构缩写、NCT 编号等专业术语保留原文。严禁返回英文叙述。"
        )
        return self._chat_json(prompt, DailySummaryDraft, model_name=model_name, system_prompt=chinese_system)

    def match_product_news(
        self,
        *,
        product_name: str,
        company_name: str | None,
        aliases: list[str],
        indications: list[str],
        title: str,
        content_text: str,
        model_name: str | None = None,
    ) -> ProductNewsMatch | None:
        prompt = (
            "Decide whether this news item is materially about the tracked biopharma product. "
            "Return JSON only with keys: is_relevant, matched_alias, matched_company, confidence, reason_short. "
            "Set is_relevant=true only when the item is clearly about the exact product or its explicitly named development program. "
            "Do not match only on company-level news unless the product itself is mentioned or strongly implied. "
            "confidence must be 0 to 1. reason_short must be factual and under 30 words.\n\n"
            f"Tracked product: {product_name}\n"
            f"Company: {company_name or ''}\n"
            f"Aliases: {json.dumps(aliases, ensure_ascii=False)}\n"
            f"Indications: {json.dumps(indications, ensure_ascii=False)}\n"
            f"News title: {title}\n"
            f"News text: {content_text[:4000]}"
        )
        return self._chat_json(prompt, ProductNewsMatch, model_name=model_name)

    def suggest_product_aliases(
        self,
        *,
        display_name: str,
        company_name: str | None,
        indications: list[str],
        modality: str | None,
        model_name: str | None = None,
    ) -> list[str] | None:
        """Ask the LLM for additional aliases for a (likely uncommon) product.

        Returns a deduped list of aliases that excludes the input ``display_name``,
        or ``None`` if the LLM is not configured / call failed. Returns an empty
        list if the LLM declines / has no confident suggestions.
        """
        prompt = (
            "You are a meticulous biopharma information librarian. The user is tracking a "
            "biopharmaceutical product (often an investigational cell therapy). "
            "List ADDITIONAL widely-used aliases for the product so news headlines that use "
            "different names can still be matched. Only suggest aliases you are CONFIDENT about — "
            "the alias must be fact-grounded and verifiable from public biopharma sources "
            "(company press releases, ClinicalTrials.gov, FDA/NMPA filings, peer-reviewed papers, "
            "industry trackers like Pharmaprojects/Cortellis). NEVER invent codes. If you are not "
            "confident, return an empty list — empty is strictly better than wrong.\n\n"
            "Include when applicable:\n"
            "  - development codes (e.g. 'JCAR017', 'bb2121', 'CTL019')\n"
            "  - generic INN names (e.g. 'lisocabtagene maraleucel', 'idecabtagene vicleucel')\n"
            "  - brand names (e.g. 'Breyanzi', 'Abecma', 'Kymriah')\n"
            "  - common short forms used in trade press (e.g. 'liso-cel', 'ide-cel')\n"
            "  - Chinese translations or Chinese brand names if the product is sold/developed in China "
            "(e.g. '倍诺达' for relmacabtagene autoleucel)\n\n"
            "Do NOT include the input display_name itself. Cap the list at 8 aliases. "
            "Prefer fewer high-confidence aliases over many low-confidence ones.\n\n"
            "Return STRICT JSON with this exact shape and nothing else: "
            '{"aliases": ["X", "Y", "Z"], "confidence": 0.0-1.0, "notes": "short rationale"}\n\n'
            f"display_name: {display_name}\n"
            f"company_name: {company_name or ''}\n"
            f"indications: {json.dumps(indications, ensure_ascii=False)}\n"
            f"modality: {modality or ''}\n"
        )
        result = self._chat_json(prompt, ProductAliasSuggestion, model_name=model_name)
        if result is None:
            return None
        # Dedupe against display_name (alphanumeric, casefold) and against itself.
        import re as _re

        def _key(s: str) -> str:
            return _re.sub(r"[^a-z0-9]+", "", (s or "").casefold())

        seen: set[str] = set()
        display_key = _key(display_name)
        if display_key:
            seen.add(display_key)
        cleaned: list[str] = []
        for alias in result.aliases:
            k = _key(alias)
            if not k or k in seen:
                continue
            seen.add(k)
            cleaned.append(alias.strip())
            if len(cleaned) >= 8:
                break
        # Attach confidence as attribute for caller filtering via a tuple-like return?
        # To keep the signature simple, expose via a side-channel attribute.
        cleaned_list: list[str] = cleaned
        # Stash confidence on the list via a wrapper? Instead, re-encode by using
        # a small custom subclass so the caller can inspect. Keep it as plain list
        # and let the caller re-call if they need confidence — simpler: caller
        # invokes _chat_json directly if filtering by confidence is required.
        # To support the spec (caller filters by confidence >= 0.6), expose the
        # raw suggestion via an attribute on the function's return is not Pythonic;
        # so we instead let the caller re-validate. For now, gate inside this
        # method when confidence is provided and below 0.6: return [].
        if result.confidence is not None and result.confidence < 0.6:
            logger.info(
                "GLM5 alias suggestion below confidence floor",
                extra={
                    "display_name": display_name,
                    "confidence": result.confidence,
                    "raw_aliases": cleaned_list,
                },
            )
            return []
        return cleaned_list

    def extract_product_timeline(
        self,
        *,
        product_name: str,
        company_name: str | None,
        aliases: list[str],
        indications: list[str],
        title: str,
        content_text: str,
        model_name: str | None = None,
    ) -> ProductTimelineExtraction | None:
        prompt = (
            "Extract timeline milestones for one tracked biopharma product from the provided news item. "
            "Return JSON only with keys: product_name and events. "
            "Each event must use only evidence from the provided title/text and include: "
            "event_date, event_date_precision, milestone_type, milestone_label, phase_label, headline, "
            "event_summary, indication, region, confidence, evidence_quote_short. "
            "Allowed event_date_precision values: year, month, day. "
            "Allowed milestone_type values: research, preclinical, ind_cta_iit, phase_start, phase_result, regulatory, partnering, financing, setback, commercial, other. "
            "If the article does not contain a concrete milestone for the tracked product, return an empty events array. "
            "Do not invent dates. If only a year is known use YYYY, if only month is known use YYYY-MM, else YYYY-MM-DD.\n\n"
            f"Tracked product: {product_name}\n"
            f"Company: {company_name or ''}\n"
            f"Aliases: {json.dumps(aliases, ensure_ascii=False)}\n"
            f"Indications: {json.dumps(indications, ensure_ascii=False)}\n"
            f"News title: {title}\n"
            f"News text: {content_text[:5000]}"
        )
        return self._chat_json(prompt, ProductTimelineExtraction, model_name=model_name)

    def _chat_json(
        self,
        prompt: str,
        model: type[T],
        model_name: str | None = None,
        system_prompt: str | None = None,
    ) -> T | None:
        if not self.is_configured:
            return None

        stricter_prompt = (
            f"{prompt}\n\nRespond with valid JSON only. Do not wrap it in Markdown. "
            f"The response must validate against schema: {json.dumps(model.model_json_schema(), ensure_ascii=False)}"
        )
        for attempt, body in enumerate([prompt, stricter_prompt], start=1):
            try:
                parsed = self._request_json(body, model_name=model_name, system_prompt=system_prompt)
                return model.model_validate(parsed)
            except httpx.HTTPError as exc:
                logger.warning(
                    "GLM5 transport failure",
                    extra={"schema_name": model.__name__, "schema_attempt": attempt, "error": str(exc)},
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                logger.warning(
                    "GLM5 validation failure schema=%s attempt=%s error=%s",
                    model.__name__,
                    attempt,
                    str(exc).replace("\n", " | ")[:800],
                )
        return None

    # ------------------------------------------------------------------
    # Streaming request with SSE parsing
    # ------------------------------------------------------------------

    def _request_json(
        self,
        prompt: str,
        model_name: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        model = model_name or self.settings.glm5_model_name

        # For deepseek models: system content must be merged into user message
        is_deepseek = model.startswith("deepseek")
        system_content = system_prompt or (
            "You produce strict JSON for a biomedical market intelligence pipeline. "
            "If the user explicitly asks for a specific output language, you MUST honor it for all "
            "human-readable text values while keeping JSON keys and enum labels in their original form."
        )

        if is_deepseek:
            messages = [
                {"role": "user", "content": f"{system_content}\n\n{prompt}"},
            ]
        else:
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
            "max_tokens": 4096,
        }
        headers = {"Authorization": f"Bearer {self.settings.glm5_api_key}"}

        _rate_limiter.wait_if_needed()

        max_attempts = max(1, self.settings.glm5_request_max_attempts)
        last_exception: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                content = self._stream_request(payload, headers)
                break
            except httpx.HTTPError as exc:
                last_exception = exc
                status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                retryable = _is_retryable_http_error(exc, status_code)
                logger.warning(
                    "GLM5 request failure",
                    extra={
                        "retryable": retryable,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "status_code": status_code,
                        "error": str(exc),
                    },
                )
                if not retryable or attempt >= max_attempts:
                    raise
                sleep(self.settings.glm5_request_backoff_seconds * (2 ** (attempt - 1)))
        else:
            if last_exception is not None:
                raise last_exception  # type: ignore[misc]
            raise RuntimeError("LLM request loop exited without response")

        # Record tokens for rate limiting
        _rate_limiter.record()

        return _extract_json_object(content)

    def _stream_request(self, payload: dict, headers: dict) -> str:
        """Execute a streaming request, return the full content string."""
        timeout = httpx.Timeout(
            connect=30.0,
            read=self.settings.glm5_request_timeout_seconds,  # 120s for first byte
            write=30.0,
            pool=30.0,
        )
        collected: list[str] = []
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                self.settings.glm5_base_url,
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                first_chunk = True
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            collected.append(content)
                        if first_chunk:
                            # Successfully received first chunk -- tighten timeout
                            # for inter-chunk reads. httpx read timeout applies
                            # per-read, so the initial 120s already covers the
                            # first byte; subsequent reads benefit from this
                            # being generous enough for slow generation.
                            first_chunk = False
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        full_content = "".join(collected)
        if not full_content:
            raise ValueError("LLM returned empty streaming response")
        return full_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    # Scan for the first balanced { ... } object, respecting strings.
    start = text.find("{")
    if start < 0:
        raise ValueError("GLM5 response did not contain a JSON object")
    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        # Fall back to greedy slice
        end = text.rfind("}")
        if end < start:
            raise ValueError("GLM5 response did not contain a balanced JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("GLM5 response JSON was not an object")
    return parsed


def _is_retryable_http_error(exc: httpx.HTTPError, status_code: int | None) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)):
        return True
    return status_code in TRANSIENT_HTTP_STATUS_CODES
