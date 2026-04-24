"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SkeletonCard } from "@/components/skeleton-card";
import { ThemeToggle } from "@/components/theme-toggle";
import { TopNav } from "@/components/top-nav";
import type { CategoriesResponse, ModelInfo, ModelsResponse, NewsListResponse, TodaySummaryResponse } from "@/lib/types";

type LoadState = "idle" | "loading" | "ready" | "error";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH || "/api";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDate(value: string | null | undefined) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(value));
}

function formatDateInput(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin text-apple-blue`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx={12} cy={12} r={10} stroke="currentColor" strokeWidth={4} />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function Dashboard() {
  const [state, setState] = useState<LoadState>("idle");
  const [categories, setCategories] = useState<string[]>([]);
  const [summary, setSummary] = useState<TodaySummaryResponse | null>(null);
  const [news, setNews] = useState<NewsListResponse | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedDate, setSelectedDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedSummaryCategory, setSelectedSummaryCategory] = useState<string | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [currentModel, setCurrentModel] = useState<string>("");
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const summaryStackRef = useRef<HTMLDivElement | null>(null);
  const eventsBubbleRef = useRef<HTMLDivElement | null>(null);
  const summaryAreaRef = useRef<HTMLDivElement | null>(null);
  const [bubbleTop, setBubbleTop] = useState<number | null>(null);

  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    setIsSearching(true);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setActiveSearch(value);
      setCurrentPage(1);
      setIsSearching(false);
    }, 400);
  }, []);

  const handleCategoryChange = useCallback((category: string | null) => {
    setSelectedCategory(category);
    setCurrentPage(1);
  }, []);

  const handleModelChange = useCallback(async (modelId: string) => {
    setCurrentModel(modelId);
    setModelMenuOpen(false);
    setRegenerating(true);
    try {
      const params = new URLSearchParams({ model: modelId });
      if (selectedDate) params.set("date", selectedDate);
      const response = await fetch(`${API_BASE_PATH}/summary/regenerate?${params.toString()}`, {
        method: "POST",
        cache: "no-store",
      });
      if (response.ok) {
        const newSummary = (await response.json()) as TodaySummaryResponse;
        setSummary(newSummary);
      }
    } catch { /* regeneration failure is non-fatal */ }
    setRegenerating(false);
  }, [selectedDate]);

  useEffect(() => {
    if (!modelMenuOpen) return;
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest("[data-model-menu]")) setModelMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [modelMenuOpen]);

  useEffect(() => {
    if (!selectedSummaryCategory) return;
    const handleClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (eventsBubbleRef.current?.contains(target)) return;
      if (summaryStackRef.current?.contains(target)) return;
      setSelectedSummaryCategory(null);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [selectedSummaryCategory]);

  useLayoutEffect(() => {
    if (!selectedSummaryCategory) {
      setBubbleTop(null);
      return;
    }
    const compute = () => {
      const area = summaryAreaRef.current;
      const bubble = eventsBubbleRef.current;
      if (!area || !bubble) return;
      const tile = area.querySelector<HTMLElement>(
        `[data-summary-category="${CSS.escape(selectedSummaryCategory)}"]`,
      );
      if (!tile) return;
      const tileRect = tile.getBoundingClientRect();
      const areaRect = area.getBoundingClientRect();
      const bubbleHeight = bubble.offsetHeight;
      const tileCenter = tileRect.top - areaRect.top + tileRect.height / 2;
      const areaHeight = area.offsetHeight;
      const proposedTop = tileCenter - bubbleHeight / 2;
      const clamped = Math.max(0, Math.min(proposedTop, Math.max(0, areaHeight - bubbleHeight)));
      setBubbleTop(clamped);
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [selectedSummaryCategory]);

  useEffect(() => {
    let cancelled = false;
    async function loadMeta() {
      try {
        const summaryParams = new URLSearchParams();
        if (selectedDate) summaryParams.set("date", selectedDate);
        const [categoryResponse, summaryResponse] = await Promise.all([
          fetch(`${API_BASE_PATH}/categories`, { cache: "no-store" }),
          fetch(`${API_BASE_PATH}/news/today-summary${summaryParams.toString() ? `?${summaryParams}` : ""}`, { cache: "no-store" }),
        ]);
        if (!categoryResponse.ok || !summaryResponse.ok) return;
        const [categoryData, summaryData] = (await Promise.all([
          categoryResponse.json(),
          summaryResponse.json(),
        ])) as [CategoriesResponse, TodaySummaryResponse];
        if (!cancelled) {
          setCategories(categoryData.categories);
          setSummary(summaryData);
        }
      } catch { /* meta fetch failure is non-fatal */ }
      try {
        const modelsResponse = await fetch(`${API_BASE_PATH}/models`, { cache: "no-store" });
        if (modelsResponse.ok) {
          const modelsData = (await modelsResponse.json()) as ModelsResponse;
          if (!cancelled) {
            setModels(modelsData.models);
            if (!currentModel) setCurrentModel(modelsData.current);
          }
        }
      } catch { /* models fetch non-fatal */ }
    }
    loadMeta();
    return () => { cancelled = true; };
  }, [reloadKey, selectedDate]);

  useEffect(() => {
    let cancelled = false;
    async function loadNews() {
      setState("loading");
      setError(null);
      const params = new URLSearchParams({ page: String(currentPage), page_size: "20" });
      if (selectedCategory) params.set("category", selectedCategory);
      if (activeSearch.trim()) params.set("q", activeSearch.trim());
      if (selectedDate) params.set("date", selectedDate);
      try {
        const newsResponse = await fetch(`${API_BASE_PATH}/news?${params.toString()}`, { cache: "no-store" });
        if (!newsResponse.ok) throw new Error("Failed to load news data.");
        const newsData = (await newsResponse.json()) as NewsListResponse;
        if (!cancelled) { setNews(newsData); setState("ready"); }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Unknown dashboard error.");
          setState("error");
        }
      }
    }
    loadNews();
    return () => { cancelled = true; };
  }, [selectedCategory, activeSearch, currentPage, selectedDate, reloadKey]);

  const todayLabel = useMemo(
    () => new Intl.DateTimeFormat(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" }).format(new Date()),
    [],
  );

  const isLoading = state === "loading" || state === "idle";
  const totalPages = news?.pagination.total_pages ?? 1;
  const activeModelId = currentModel || summary?.model_name || "";

  return (
    <main className="min-h-screen bg-apple-gray text-apple-text dark:bg-apple-black dark:text-white">
      {/* ── Header / Translucent Glass Nav ── */}
      <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-[20px] backdrop-saturate-150 text-white">
        <div className="mx-auto flex h-12 w-full max-w-[980px] items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-3">
            <Link className="font-display text-[17px] font-semibold tracking-tight" href="/">
              Biomed / Cell Therapy Daily
            </Link>
            <span className="hidden text-xs text-white/60 sm:inline">{todayLabel}</span>
          </div>
          <div className="hidden sm:block">
            <TopNav />
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="hidden text-white/60 md:inline">
              Updated {formatDateTime(news?.last_updated_at)}
            </span>
            <span
              className={`hidden rounded-pill px-2.5 py-1 text-[11px] font-medium md:inline-flex ${
                state === "error"
                  ? "bg-[#ff3b30]/90 text-white"
                  : isLoading
                    ? "bg-white/10 text-white/80"
                    : "bg-apple-blue/90 text-white"
              }`}
            >
              {state === "error" ? "Refresh failed" : isLoading ? "Refreshing" : "Ready"}
            </span>
            <Button
              aria-label="Refresh data"
              className="h-8 w-8 !px-0"
              onClick={() => setReloadKey((v) => v + 1)}
              type="button"
              variant="ghost"
            >
              <svg aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path d="M4 4v5h5M20 20v-5h-5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L4 4m16 16-1.64-1.64A9 9 0 0 1 3.51 15" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* ── Error State ── */}
      {state === "error" ? (
        <section className="bg-apple-black text-white">
          <div className="mx-auto w-full max-w-[980px] px-4 py-20 text-center">
            <h2 className="font-display text-[40px] font-semibold leading-[1.1] tracking-tight">
              We couldn&rsquo;t load today&rsquo;s briefing
            </h2>
            <p className="mx-auto mt-4 max-w-[640px] text-[17px] font-light text-white/70">
              {error}
            </p>
            <div className="mt-8 flex justify-center">
              <Button
                className="rounded-pill px-[22px]"
                onClick={() => setReloadKey((v) => v + 1)}
                type="button"
              >
                Try again
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {/* ── Hero / Daily Summary (black) ── */}
      <section aria-labelledby="daily-summary-title" className="bg-apple-black text-white">
        <div className="mx-auto w-full max-w-[980px] px-4 py-20">
          <div className="text-center">
            <p className="font-display text-[17px] font-light text-white/70">Daily intelligence</p>
            <h1
              id="daily-summary-title"
              className="mt-3 font-display text-[40px] font-semibold leading-[1.07] tracking-tight sm:text-[48px] lg:text-[56px]"
            >
              {summary?.summary_date ? formatDate(summary.summary_date) : "Today in biomed"}
            </h1>
            <p className="mx-auto mt-4 max-w-[640px] text-[19px] font-light text-white/70">
              A curated briefing across cell therapy, biotech finance, clinical readouts, and regulatory news.
            </p>

            {/* Date picker + model selector */}
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <label className="inline-flex items-center gap-2 rounded-pill border border-white/25 bg-transparent px-[18px] py-2 text-sm text-white/90 transition-colors hover:border-white/50">
                <span className="text-white/60">Date</span>
                <input
                  aria-label="Select date"
                  className="bg-transparent text-sm text-white outline-none [color-scheme:dark]"
                  max={formatDateInput(new Date())}
                  onChange={(e) => { setSelectedDate(e.target.value); setCurrentPage(1); }}
                  type="date"
                  value={selectedDate}
                />
              </label>

              <div className="relative" data-model-menu>
                <button
                  className="inline-flex items-center gap-2 rounded-pill border border-apple-linkDark bg-transparent px-[18px] py-2 text-sm text-apple-linkDark transition-colors hover:bg-apple-linkDark/10"
                  onClick={() => setModelMenuOpen(!modelMenuOpen)}
                  type="button"
                >
                  {regenerating ? (
                    <Spinner className="h-3.5 w-3.5" />
                  ) : (
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                    </svg>
                  )}
                  <span>{activeModelId || "Model"}</span>
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                  </svg>
                </button>

                {modelMenuOpen && (
                  <div className="absolute left-1/2 z-50 mt-2 w-72 -translate-x-1/2 rounded-lg bg-apple-darkSurface1 py-2 text-left shadow-apple">
                    {models.map((m) => {
                      const isActive = activeModelId === m.id;
                      return (
                        <button
                          key={m.id}
                          className={`flex w-full flex-col gap-0.5 px-4 py-2 text-left transition-colors hover:bg-white/5 ${
                            isActive ? "text-apple-linkDark" : "text-white"
                          }`}
                          onClick={() => handleModelChange(m.id)}
                          type="button"
                        >
                          <span className="flex items-center gap-2 text-sm font-medium">
                            {m.id}
                            {isActive ? (
                              <svg className="ml-auto h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                              </svg>
                            ) : null}
                          </span>
                          <span className="text-xs text-white/60">{m.label} &middot; {m.type}</span>
                          <span className="text-xs text-white/40">{m.description}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Summary body */}
          <div className="mt-12">
            {regenerating ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12">
                <Spinner className="h-6 w-6" />
                <span className="text-sm text-white/70">Regenerating with {currentModel}&hellip;</span>
              </div>
            ) : isLoading && !summary ? (
              <div className="mx-auto max-w-[720px] space-y-3">
                <div className="h-4 w-full animate-pulse rounded bg-white/10" />
                <div className="h-4 w-4/5 animate-pulse rounded bg-white/10" />
                <div className="h-4 w-2/3 animate-pulse rounded bg-white/10" />
              </div>
            ) : summary?.available ? (
              <div className="relative" ref={summaryAreaRef}>
                <div
                  ref={summaryStackRef}
                  className={`mx-auto max-w-[640px] space-y-6 transition-transform duration-500 ease-apple ${
                    selectedSummaryCategory ? "lg:-translate-x-[220px]" : "lg:translate-x-0"
                  }`}
                >
                  <p className="text-left text-[19px] font-light leading-[1.47] text-white/85">
                    {summary.daily_summary}
                  </p>

                  {summary.category_summaries && Object.keys(summary.category_summaries).length > 0 ? (
                    <div className="space-y-3">
                      {Object.entries(summary.category_summaries).map(([cat, text]) => {
                        const isActive = selectedSummaryCategory === cat;
                        return (
                          <button
                            key={cat}
                            aria-controls="events-bubble"
                            aria-expanded={isActive}
                            data-summary-category={cat}
                            className={`w-full rounded-lg p-4 text-left transition-colors ${
                              isActive
                                ? "bg-apple-blue/15 ring-1 ring-apple-linkDark"
                                : "bg-apple-darkSurface1 hover:bg-apple-darkSurface2"
                            }`}
                            onClick={() => setSelectedSummaryCategory(isActive ? null : cat)}
                            type="button"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="font-display text-xs font-semibold uppercase tracking-wide text-apple-linkDark">
                                {cat}
                              </p>
                              <span
                                aria-hidden="true"
                                className={`text-base leading-none text-white/50 transition-transform duration-300 ease-apple ${
                                  isActive ? "rotate-90" : "rotate-0"
                                }`}
                              >
                                &rsaquo;
                              </span>
                            </div>
                            <p className="mt-2 text-left text-sm leading-[1.47] text-white/85">{text}</p>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}

                  {summary.trend_signal ? (
                    <div className="rounded-lg bg-apple-darkSurface1 p-4">
                      <p className="font-display text-xs font-semibold uppercase tracking-wide text-apple-linkDark">
                        Trend signal
                      </p>
                      <p className="mt-2 text-left text-sm leading-[1.47] text-white/85">{summary.trend_signal}</p>
                    </div>
                  ) : null}
                </div>

                <div
                  aria-hidden={!selectedSummaryCategory}
                  aria-label={selectedSummaryCategory ? `${selectedSummaryCategory} events` : undefined}
                  id="events-bubble"
                  ref={eventsBubbleRef}
                  role="region"
                  style={selectedSummaryCategory && bubbleTop != null ? { top: `${bubbleTop}px` } : undefined}
                  className={[
                    "rounded-2xl bg-apple-darkSurface1 p-5 shadow-apple",
                    "static mt-6 lg:absolute lg:right-0 lg:top-0 lg:mt-0 lg:block lg:w-[360px] lg:transition-all lg:duration-500 lg:ease-apple",
                    selectedSummaryCategory
                      ? "block animate-fade-in lg:translate-x-0 lg:scale-100 lg:opacity-100 lg:pointer-events-auto"
                      : "hidden lg:translate-x-6 lg:scale-95 lg:opacity-0 lg:pointer-events-none",
                  ].join(" ")}
                >
                  {selectedSummaryCategory ? (
                    <>
                      <div className="mb-4 flex items-center justify-between">
                        <p className="font-display text-xs font-semibold uppercase tracking-wide text-apple-linkDark">
                          {selectedSummaryCategory} events
                        </p>
                        <span className="text-[11px] font-medium text-white/40">
                          {summary.top_events.filter((e) => e.category === selectedSummaryCategory).length}
                        </span>
                      </div>
                      <ol key={selectedSummaryCategory} className="max-h-[60vh] space-y-3 overflow-y-auto animate-fade-in">
                        {summary.top_events.filter((e) => e.category === selectedSummaryCategory).map((event) => (
                          <li key={`${event.title}-${event.canonical_url}`} className="rounded-lg bg-apple-darkSurface3 p-3 transition-colors hover:bg-black/40">
                            <a
                              className="text-left text-sm font-medium leading-[1.43] text-white hover:text-apple-linkDark"
                              href={event.canonical_url}
                              rel="noreferrer"
                              target="_blank"
                            >
                              {event.title}
                            </a>
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <Badge variant="secondary">{event.category}</Badge>
                              {event.source_name ? <span className="text-xs text-white/60">{event.source_name}</span> : null}
                              {event.published_at ? <span className="text-xs text-white/40">{formatDateTime(event.published_at)}</span> : null}
                            </div>
                          </li>
                        ))}
                        {summary.top_events.filter((e) => e.category === selectedSummaryCategory).length === 0 ? (
                          <li className="text-sm text-white/60">No top events for this category.</li>
                        ) : null}
                      </ol>
                    </>
                  ) : null}
                </div>
              </div>
            ) : (
              <p className="text-center text-[17px] font-light text-white/70">
                No daily summary is available for this date.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ── Search + Category Filters (light) ── */}
      <section aria-label="Search and filters" className="bg-apple-gray dark:bg-apple-black">
        <div className="mx-auto w-full max-w-[980px] px-4 py-12">
          <div className="mx-auto max-w-[640px]">
            <label className="relative block">
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-apple-text/50 dark:text-white/50"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <circle cx={11} cy={11} r={8} />
                <path d="m21 21-4.35-4.35" strokeLinecap="round" />
              </svg>
              <input
                aria-label="Search news"
                className="w-full rounded-pill bg-white py-2.5 pl-11 pr-4 text-sm text-apple-text placeholder:text-apple-text/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue dark:bg-apple-darkSurface1 dark:text-white dark:placeholder:text-white/50"
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search by title, source, or summary"
                type="search"
                value={searchQuery}
              />
            </label>
            <div className="mt-1.5 h-4 text-center">
              {isSearching ? (
                <span className="text-[12px] text-apple-text/60 dark:text-white/60">
                  {"\u6b63\u5728\u641c\u7d22\u2026"}
                </span>
              ) : null}
            </div>
          </div>

          <div className="mt-8 flex justify-center">
            <div className="flex max-w-full gap-2 overflow-x-auto px-1 pb-2 scrollbar-thin">
              <button
                aria-pressed={selectedCategory === null}
                className="shrink-0"
                onClick={() => handleCategoryChange(null)}
                type="button"
              >
                <Badge
                  variant={selectedCategory === null ? "default" : "outline"}
                  className="cursor-pointer rounded-pill px-4 py-1.5 text-sm"
                >
                  All{news ? ` (${news.pagination.total_items})` : ""}
                </Badge>
              </button>
              {categories.map((category) => {
                const count = news?.category_counts?.[category];
                const isActive = selectedCategory === category;
                return (
                  <button
                    aria-pressed={isActive}
                    className="shrink-0"
                    key={category}
                    onClick={() => handleCategoryChange(category)}
                    type="button"
                  >
                    <Badge
                      variant={isActive ? "default" : "outline"}
                      className="cursor-pointer rounded-pill px-4 py-1.5 text-sm"
                    >
                      {category}{count != null ? ` (${count})` : ""}
                    </Badge>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ── News Feed (light) ── */}
      <section aria-labelledby="news-feed-title" className="bg-apple-gray dark:bg-apple-black">
        <div className="mx-auto w-full max-w-[980px] px-4 pb-20">
          <div className="mb-8 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <h2
                id="news-feed-title"
                className="font-display text-[28px] font-semibold leading-[1.14] tracking-tight text-apple-text dark:text-white"
              >
                News feed
              </h2>
              <p className="mt-2 text-sm text-apple-text/60 dark:text-white/60">
                {news ? `${news.pagination.total_items} items \u00b7 Page ${news.pagination.page} of ${news.pagination.total_pages}` : "Loading items"}
              </p>
            </div>
          </div>

          {(selectedCategory || activeSearch || selectedDate) ? (
            <div className="mb-6 flex flex-wrap items-center gap-2 text-[12px] text-apple-text/70 dark:text-white/70">
              <span className="font-medium">{"\u5df2\u7b5b\u9009\uff1a"}</span>
              {selectedCategory ? (
                <span className="inline-flex items-center gap-1 rounded-pill bg-apple-blue/10 px-2.5 py-0.5 text-apple-text dark:bg-apple-blue/20 dark:text-white">
                  {`\u5206\u7c7b: ${selectedCategory}`}
                  <button
                    aria-label="Clear category filter"
                    className="ml-0.5 text-apple-text/60 hover:text-apple-text dark:text-white/60 dark:hover:text-white"
                    onClick={() => handleCategoryChange(null)}
                    type="button"
                  >
                    &times;
                  </button>
                </span>
              ) : null}
              {activeSearch ? (
                <span className="inline-flex items-center gap-1 rounded-pill bg-apple-blue/10 px-2.5 py-0.5 text-apple-text dark:bg-apple-blue/20 dark:text-white">
                  {`\u641c\u7d22: "${activeSearch}"`}
                  <button
                    aria-label="Clear search filter"
                    className="ml-0.5 text-apple-text/60 hover:text-apple-text dark:text-white/60 dark:hover:text-white"
                    onClick={() => handleSearchChange("")}
                    type="button"
                  >
                    &times;
                  </button>
                </span>
              ) : null}
              {selectedDate ? (
                <span className="inline-flex items-center gap-1 rounded-pill bg-apple-blue/10 px-2.5 py-0.5 text-apple-text dark:bg-apple-blue/20 dark:text-white">
                  {`\u65e5\u671f: ${selectedDate}`}
                  <button
                    aria-label="Clear date filter"
                    className="ml-0.5 text-apple-text/60 hover:text-apple-text dark:text-white/60 dark:hover:text-white"
                    onClick={() => { setSelectedDate(""); setCurrentPage(1); }}
                    type="button"
                  >
                    &times;
                  </button>
                </span>
              ) : null}
            </div>
          ) : null}

          {isLoading ? (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <SkeletonCard key={index} />
              ))}
            </div>
          ) : news && news.items.length > 0 ? (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
              {news.items.map((item) => (
                <Card
                  className="animate-fade-in group flex flex-col overflow-hidden transition-shadow duration-300 hover:shadow-apple"
                  key={item.id}
                >
                  {item.image_url ? (
                    <div className="relative h-44 w-full overflow-hidden rounded-xl bg-apple-gray dark:bg-apple-darkSurface1">
                      <img
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                        src={item.image_url}
                      />
                    </div>
                  ) : null}
                  <CardContent className="flex flex-1 flex-col gap-3">
                    <div className="flex items-start justify-between gap-3">
                      <Badge variant="secondary">{item.category}</Badge>
                      <span className="shrink-0 text-xs text-apple-text/50 dark:text-white/50">
                        {formatDateTime(item.published_at)}
                      </span>
                    </div>
                    <h3 className="font-display text-[21px] font-semibold leading-[1.19] tracking-tight text-apple-text dark:text-white">
                      <a
                        className="hover:text-apple-link dark:hover:text-apple-linkDark"
                        href={item.canonical_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {item.title}
                      </a>
                    </h3>
                    <p className="text-xs font-medium uppercase tracking-wide text-apple-text/55 dark:text-white/55">
                      {item.source_name}
                    </p>
                    <p className="flex-1 text-sm leading-[1.43] text-apple-text/80 dark:text-white/80">
                      {item.short_summary}
                    </p>
                    {item.entities && item.entities.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {item.entities.slice(0, 5).map((entity) => (
                          <span
                            className="inline-block rounded-pill bg-[#ededf2] px-2.5 py-0.5 text-xs text-apple-text/75 dark:bg-apple-darkSurface1 dark:text-white/75"
                            key={entity}
                          >
                            {entity}
                          </span>
                        ))}
                        {item.entities.length > 5 ? (
                          <span className="inline-block rounded-pill bg-[#ededf2] px-2.5 py-0.5 text-xs text-apple-text/50 dark:bg-apple-darkSurface1 dark:text-white/50">
                            +{item.entities.length - 5}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="mt-2 flex items-center justify-between">
                      <a
                        className="text-sm font-medium text-apple-link hover:underline dark:text-apple-linkDark"
                        href={item.canonical_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Learn more &rsaquo;
                      </a>
                      <div className="flex items-center gap-1.5">
                        {item.relevance_to_cell_therapy != null && item.relevance_to_cell_therapy >= 0.7 ? (
                          <Badge variant="default" className="text-[10px]">High relevance</Badge>
                        ) : null}
                        {item.importance_score != null && item.importance_score >= 0.7 ? (
                          <Badge variant="secondary" className="text-[10px]">
                            {`\u2605 \u9ad8\u4ef7\u503c ${item.importance_score.toFixed(2)}`}
                          </Badge>
                        ) : null}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="mx-auto max-w-[640px] py-16 text-center">
              <h3 className="font-display text-[28px] font-semibold leading-[1.14] tracking-tight text-apple-text dark:text-white">
                Nothing here yet
              </h3>
              <p className="mt-3 text-[17px] font-light text-apple-text/70 dark:text-white/70">
                No news items match the current filters.
              </p>
              {(selectedCategory || activeSearch || selectedDate) ? (
                <p className="mt-2 text-[13px] text-apple-text/60 dark:text-white/60">
                  {`\u5728\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u65e0\u7ed3\u679c\uff1a${[
                    selectedCategory ? `\u5206\u7c7b: ${selectedCategory}` : null,
                    activeSearch ? `\u641c\u7d22: "${activeSearch}"` : null,
                    selectedDate ? `\u65e5\u671f: ${selectedDate}` : null,
                  ].filter(Boolean).join(" \u00b7 ")}`}
                </p>
              ) : null}
              <div className="mt-6">
                <Button
                  className="rounded-pill px-[22px]"
                  onClick={() => { handleCategoryChange(null); handleSearchChange(""); }}
                  type="button"
                >
                  Clear filters
                </Button>
              </div>
            </div>
          )}

          {/* ── Pagination ── */}
          {news && totalPages > 1 ? (
            <nav aria-label="Pagination" className="mt-12 flex items-center justify-center gap-2">
              <Button
                className="rounded-pill px-[22px]"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                type="button"
                variant="outline"
              >
                &larr; Prev
              </Button>
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                let page: number;
                if (totalPages <= 7) { page = i + 1; }
                else if (currentPage <= 4) { page = i + 1; }
                else if (currentPage >= totalPages - 3) { page = totalPages - 6 + i; }
                else { page = currentPage - 3 + i; }
                const isActive = currentPage === page;
                return (
                  <Button
                    className="min-w-[2.5rem] rounded-pill px-[22px]"
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    type="button"
                    variant={isActive ? "default" : "outline"}
                  >
                    {page}
                  </Button>
                );
              })}
              <Button
                className="rounded-pill px-[22px]"
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                type="button"
                variant="outline"
              >
                Next &rarr;
              </Button>
            </nav>
          ) : null}
        </div>
      </section>

      {/* ── Footer (dark) ── */}
      <footer className="bg-apple-black text-white/60">
        <div className="mx-auto w-full max-w-[980px] px-4 py-12 text-center">
          <p className="text-xs leading-[1.33]">
            Biomed / Cell Therapy Daily Intelligence &middot; Data sourced from Fierce Biotech, BioPharma Dive, GEN, Nature
          </p>
          <p className="mt-2 text-xs leading-[1.33]">
            AI-powered classification and summarization &middot; Updated 3&times; daily
          </p>
        </div>
      </footer>
    </main>
  );
}
