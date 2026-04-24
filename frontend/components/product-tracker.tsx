"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";
import { TopNav } from "@/components/top-nav";
import type {
  ProductCreateRequest,
  ProductListResponse,
  TrackedProductDetail,
  TrackedProductListItem,
} from "@/lib/types";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH || "/api";

type LoadState = "idle" | "loading" | "ready" | "error";

type ProductFormState = {
  display_name: string;
  company_name: string;
  aliases: string;
  indications: string;
  modality: string;
};

const EMPTY_FORM: ProductFormState = {
  display_name: "",
  company_name: "",
  aliases: "",
  indications: "",
  modality: "",
};

function formatDateTime(value: string | null | undefined) {
  if (!value) return "尚未回填";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function parseTagInput(value: string) {
  return value
    .split(/\r?\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProductTracker() {
  const [state, setState] = useState<LoadState>("idle");
  const [items, setItems] = useState<TrackedProductListItem[]>([]);
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [form, setForm] = useState<ProductFormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const pollerRef = useRef<number | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setActiveQuery(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const hasRunning = useMemo(
    () => items.some((item) => item.backfill_status === "running"),
    [items],
  );

  useEffect(() => {
    if (!hasRunning) {
      if (pollerRef.current !== null) {
        window.clearInterval(pollerRef.current);
        pollerRef.current = null;
      }
      return;
    }
    if (pollerRef.current !== null) return;
    pollerRef.current = window.setInterval(async () => {
      try {
        const params = new URLSearchParams();
        if (activeQuery) params.set("q", activeQuery);
        const response = await fetch(
          `${API_BASE_PATH}/products${params.toString() ? `?${params}` : ""}`,
          { cache: "no-store" },
        );
        if (!response.ok) return;
        const data = (await response.json()) as ProductListResponse;
        setItems(data.items);
        setNow(Date.now());
      } catch {
        // swallow poll errors; next tick will retry
      }
    }, 5000);
    return () => {
      if (pollerRef.current !== null) {
        window.clearInterval(pollerRef.current);
        pollerRef.current = null;
      }
    };
  }, [hasRunning, activeQuery]);

  useEffect(() => {
    if (!hasRunning) return;
    const tick = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(tick);
  }, [hasRunning]);

  useEffect(() => {
    let cancelled = false;
    async function loadProducts() {
      setState("loading");
      setError(null);
      try {
        const params = new URLSearchParams();
        if (activeQuery) params.set("q", activeQuery);
        const response = await fetch(
          `${API_BASE_PATH}/products${params.toString() ? `?${params}` : ""}`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error("Failed to load tracked products.");
        const data = (await response.json()) as ProductListResponse;
        if (!cancelled) {
          setItems(data.items);
          setState("ready");
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Unknown product tracker error.");
          setState("error");
        }
      }
    }
    loadProducts();
    return () => {
      cancelled = true;
    };
  }, [activeQuery]);

  async function handleCreateProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.display_name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: ProductCreateRequest = {
        display_name: form.display_name.trim(),
        company_name: form.company_name.trim() || null,
        aliases: parseTagInput(form.aliases),
        indications: parseTagInput(form.indications),
        modality: form.modality.trim() || null,
      };
      const response = await fetch(`${API_BASE_PATH}/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail =
          body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string"
            ? (body as { detail: string }).detail
            : null;
        throw new Error(detail || "Failed to create tracked product.");
      }
      const detail = (await response.json()) as TrackedProductDetail;
      setSuccessMessage("产品已创建，正在后台回填事件…");
      window.setTimeout(() => {
        window.location.href = `/products/${detail.slug}`;
      }, 2000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown creation error.");
      setSubmitting(false);
    }
  }

  async function handleDelete(item: TrackedProductListItem) {
    const confirmed = window.confirm(
      `确定删除已追踪产品 ${item.display_name} ？此操作不可撤销。`,
    );
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_BASE_PATH}/products/${item.id}`, {
        method: "DELETE",
      });
      if (response.status === 204) {
        setItems((prev) => prev.filter((p) => p.id !== item.id));
        return;
      }
      const body = await response.json().catch(() => null);
      const detail =
        body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string"
          ? (body as { detail: string }).detail
          : `删除失败 (HTTP ${response.status})`;
      window.alert(detail);
    } catch (caught) {
      window.alert(caught instanceof Error ? caught.message : "删除失败");
    }
  }

  const summaryLabel = useMemo(() => {
    if (items.length === 0) return "No tracked products yet";
    return `${items.length} tracked ${items.length === 1 ? "product" : "products"}`;
  }, [items]);

  const isLoading = state === "loading" || state === "idle";

  return (
    <main className="min-h-screen bg-apple-gray text-apple-text dark:bg-apple-black dark:text-white">
      {/* Glass nav — mirrors dashboard */}
      <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-[20px] backdrop-saturate-150 text-white">
        <div className="mx-auto flex h-12 w-full max-w-[980px] items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-3">
            <Link className="font-display text-[17px] font-semibold tracking-tight" href="/">
              Biomed / Cell Therapy Daily
            </Link>
          </div>
          <div className="hidden sm:block">
            <TopNav />
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="hidden text-white/60 md:inline">{summaryLabel}</span>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-apple-black text-white">
        <div className="mx-auto w-full max-w-[980px] px-4 py-20 text-center">
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-apple-linkDark">
            Product tracking
          </p>
          <h1 className="mx-auto mt-4 max-w-[720px] font-display text-[40px] font-semibold leading-[1.07] tracking-tight md:text-[48px] lg:text-[56px]">
            Keep a product&apos;s full timeline in one place.
          </h1>
          <p className="mx-auto mt-5 max-w-[620px] text-[19px] font-light leading-[1.42] text-white/75">
            Create a product profile, then backfill linked news, trial milestones, and regulatory events — all kept in sync with the daily feed.
          </p>
        </div>
      </section>

      {/* Create + list */}
      <section className="bg-apple-gray dark:bg-apple-black">
        <div className="mx-auto grid w-full max-w-[980px] gap-8 px-4 py-16 lg:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardHeader>
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-apple-text/55 dark:text-white/50">
                  New profile
                </p>
                <h2 className="font-display text-[21px] font-semibold tracking-tight">
                  Track a product
                </h2>
                <p className="text-[13px] leading-[1.4] text-apple-text/60 dark:text-white/55">
                  Name + company is enough to start. Aliases and indications improve matching.
                </p>
              </div>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleCreateProduct}>
                <Field
                  label="产品名称 Display name"
                  onChange={(value) => setForm((current) => ({ ...current, display_name: value }))}
                  placeholder="CB-010"
                  required
                  value={form.display_name}
                />
                <Field
                  label="公司名称 Company"
                  onChange={(value) => setForm((current) => ({ ...current, company_name: value }))}
                  placeholder="Caribou Biosciences"
                  value={form.company_name}
                />
                <Field
                  label="别名 Aliases"
                  onChange={(value) => setForm((current) => ({ ...current, aliases: value }))}
                  placeholder="CB010, allogeneic anti-CD19 CAR-T"
                  value={form.aliases}
                  hint="使用逗号或换行分隔"
                />
                <Field
                  label="适应症 Indications"
                  onChange={(value) => setForm((current) => ({ ...current, indications: value }))}
                  placeholder="NHL, B-cell malignancies"
                  value={form.indications}
                  hint="使用逗号或换行分隔"
                />
                <Field
                  label="治疗模态 Modality"
                  onChange={(value) => setForm((current) => ({ ...current, modality: value }))}
                  placeholder="Allogeneic CAR-T"
                  value={form.modality}
                />
                {error ? (
                  <p className="text-[13px] leading-[1.4] text-[#ff3b30]">{error}</p>
                ) : null}
                {successMessage ? (
                  <p className="rounded-md bg-[#34c759]/10 px-3 py-2 text-[13px] leading-[1.4] text-[#34c759]">
                    {successMessage}
                  </p>
                ) : null}
                <Button
                  className="w-full"
                  disabled={submitting || !form.display_name.trim()}
                  type="submit"
                >
                  {submitting ? "正在创建…" : "添加产品 Create"}
                </Button>
              </form>
            </CardContent>
          </Card>

          <section className="space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="font-display text-[21px] font-semibold tracking-tight">
                  Tracked products
                </h2>
                <p className="text-[13px] leading-[1.4] text-apple-text/60 dark:text-white/55">
                  Search by product name, company, or alias.
                </p>
              </div>
              <input
                aria-label="搜索已追踪产品"
                className="w-full max-w-[300px] rounded-pill bg-white px-5 py-2.5 text-sm text-apple-text outline-none transition-colors placeholder:text-apple-text/40 focus:ring-2 focus:ring-apple-blue dark:bg-apple-darkSurface1 dark:text-white dark:placeholder:text-white/40"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索已追踪产品"
                type="search"
                value={query}
              />
            </div>

            {isLoading ? (
              <div className="grid gap-4 md:grid-cols-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-44 animate-pulse rounded-lg bg-[#ededf2] dark:bg-apple-darkSurface1"
                  />
                ))}
              </div>
            ) : null}

            {state === "error" ? (
              <Card>
                <CardContent className="py-6 text-sm text-[#ff3b30]">{error}</CardContent>
              </Card>
            ) : null}

            {state === "ready" && items.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-sm text-apple-text/60 dark:text-white/55">
                  暂无已追踪产品，请在左侧添加
                </CardContent>
              </Card>
            ) : null}

            {state === "ready" && items.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-2">
                {items.map((item) => (
                  <Link key={item.id} href={`/products/${item.slug}`} className="group relative block">
                    <Card className="h-full transition-shadow duration-300 ease-apple hover:shadow-apple">
                      <CardContent className="flex h-full flex-col gap-4 py-5">
                        <div className="space-y-1.5">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="truncate font-display text-[19px] font-semibold tracking-tight group-hover:text-apple-link dark:group-hover:text-apple-linkDark">
                                {item.display_name}
                              </h3>
                              <p className="truncate text-[13px] text-apple-text/60 dark:text-white/55">
                                {item.company_name || "未设置公司"}
                              </p>
                            </div>
                            <div className="flex shrink-0 flex-col items-end gap-1.5">
                              <div className="flex items-center gap-2">
                                <BackfillStatusBadge item={item} now={now} />
                                <button
                                  type="button"
                                  aria-label={`删除 ${item.display_name}`}
                                  onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    void handleDelete(item);
                                  }}
                                  className="rounded-full border border-black/10 bg-white/70 p-1 text-apple-text/60 opacity-0 transition hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-500 group-hover:opacity-100 dark:border-white/15 dark:bg-black/40 dark:text-white/60 dark:hover:text-red-400"
                                >
                                  <svg
                                    aria-hidden="true"
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                  >
                                    <path d="M3 6h18" />
                                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                                    <path d="M10 11v6" />
                                    <path d="M14 11v6" />
                                  </svg>
                                </button>
                              </div>
                              <Badge variant="default" className="shrink-0">
                                {item.timeline_event_count} events
                              </Badge>
                            </div>
                          </div>
                          {item.modality ? (
                            <p className="text-[13px] text-apple-text/70 dark:text-white/65">
                              {item.modality}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {item.aliases.slice(0, 3).map((alias) => (
                            <Badge key={alias} variant="secondary" className="text-[11px]">
                              {alias}
                            </Badge>
                          ))}
                          {item.indications.slice(0, 2).map((indication) => (
                            <Badge key={indication} variant="outline" className="text-[11px]">
                              {indication}
                            </Badge>
                          ))}
                        </div>
                        <div className="mt-auto grid grid-cols-2 gap-3 text-[12px]">
                          <Metric label="关联新闻" value={String(item.linked_news_count)} />
                          <Metric label="最近回填" value={formatDateTime(item.last_backfill_at)} />
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            ) : null}
          </section>
        </div>
      </section>

      <footer className="bg-apple-black py-12 text-center text-[12px] text-white/55">
        <div className="mx-auto max-w-[980px] px-4">
          Biomed / Cell Therapy Daily · Product tracking
        </div>
      </footer>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required = false,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium uppercase tracking-[0.12em] text-apple-text/65 dark:text-white/60">
        {label}
        {required ? <span className="ml-1 text-apple-blue">*</span> : null}
      </span>
      <input
        className="w-full rounded-md bg-[#ededf2] px-3.5 py-2.5 text-[14px] text-apple-text outline-none transition-colors placeholder:text-apple-text/40 focus:ring-2 focus:ring-apple-blue dark:bg-apple-darkSurface3 dark:text-white dark:placeholder:text-white/40"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
        type="text"
        value={value}
      />
      {hint ? (
        <p className="text-[11px] text-apple-text/50 dark:text-white/45">{hint}</p>
      ) : null}
    </label>
  );
}

function BackfillStatusBadge({
  item,
  now,
}: {
  item: TrackedProductListItem;
  now: number;
}) {
  const status = item.backfill_status;
  if (status === "idle") return null;
  if (status === "running") {
    let elapsedLabel: string | null = null;
    if (item.backfill_started_at) {
      const started = new Date(item.backfill_started_at).getTime();
      if (!Number.isNaN(started)) {
        const minutes = Math.max(0, Math.floor((now - started) / 60000));
        elapsedLabel = `${minutes}m`;
      }
    }
    return (
      <span className="inline-flex items-center gap-1.5 rounded-pill bg-apple-blue/10 px-2.5 py-0.5 text-[11px] font-medium text-apple-blue dark:bg-apple-linkDark/15 dark:text-apple-linkDark">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-apple-blue dark:bg-apple-linkDark" />
        ⏳ 回填中{elapsedLabel ? ` · ${elapsedLabel}` : ""}
      </span>
    );
  }
  if (status === "done") {
    if (item.timeline_event_count === 0) {
      return (
        <span
          title="backfill completed but no matching news"
          className="inline-flex items-center gap-1 rounded-pill bg-[#ff9500]/15 px-2.5 py-0.5 text-[11px] font-medium text-[#b26a00] dark:text-[#ffb84d]"
        >
          ⚠ 未找到事件
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-pill bg-[#34c759]/15 px-2 py-0.5 text-[10px] font-medium text-[#1f8f3f] dark:text-[#6ddc88]">
        ✓ 已回填
      </span>
    );
  }
  if (status === "failed") {
    const tooltip = (item.backfill_error ?? "").slice(0, 200);
    return (
      <span
        title={tooltip || "回填失败"}
        className="inline-flex items-center gap-1 rounded-pill bg-[#ff3b30]/15 px-2.5 py-0.5 text-[11px] font-medium text-[#ff3b30]"
      >
        ✗ 回填失败
      </span>
    );
  }
  return null;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5 rounded-md bg-[#ededf2] px-3 py-2 dark:bg-apple-darkSurface1">
      <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-apple-text/55 dark:text-white/45">
        {label}
      </p>
      <p className="truncate text-[12px] text-apple-text/85 dark:text-white/80">{value}</p>
    </div>
  );
}
