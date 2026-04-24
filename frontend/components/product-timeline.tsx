"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";
import { TopNav } from "@/components/top-nav";
import type {
  ProductTimelineEvent,
  ProductTimelineResponse,
  TrackedProductDetail,
} from "@/lib/types";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH || "/api";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatEventDate(value: string, precision: string) {
  const date = new Date(value);
  if (precision === "year") {
    return String(date.getUTCFullYear());
  }
  if (precision === "month") {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "long",
      timeZone: "UTC",
    }).format(date);
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function ProductTimeline({ slug }: { slug: string }) {
  const [state, setState] = useState<LoadState>("idle");
  const [detail, setDetail] = useState<TrackedProductDetail | null>(null);
  const [timeline, setTimeline] = useState<ProductTimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);
  const pollingRef = useRef(false);

  async function loadProduct() {
    setState("loading");
    setError(null);
    try {
      const [detailResponse, timelineResponse] = await Promise.all([
        fetch(`${API_BASE_PATH}/products/${slug}`, { cache: "no-store" }),
        fetch(`${API_BASE_PATH}/products/${slug}/timeline`, { cache: "no-store" }),
      ]);
      if (!detailResponse.ok || !timelineResponse.ok) {
        throw new Error("Failed to load product timeline.");
      }
      const [detailData, timelineData] = (await Promise.all([
        detailResponse.json(),
        timelineResponse.json(),
      ])) as [TrackedProductDetail, ProductTimelineResponse];
      setDetail(detailData);
      setTimeline(timelineData);
      setState("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown product timeline error.");
      setState("error");
    }
  }

  useEffect(() => {
    loadProduct();
  }, [slug]);

  const pollBackfillStatus = useCallback(
    async (productSlug: string, startTs: number): Promise<void> => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      setBackfilling(true);
      try {
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const res = await fetch(`${API_BASE_PATH}/products/${productSlug}`, { cache: "no-store" });
          if (!res.ok) throw new Error("Failed to poll backfill status.");
          const current = (await res.json()) as TrackedProductDetail;
          const elapsedMin = Math.floor((Date.now() - startTs) / 60000);
          if (current.backfill_status === "running") {
            setBackfillMessage(`正在回填… (已运行 ${elapsedMin} 分钟)`);
            await new Promise((r) => setTimeout(r, 5000));
            continue;
          }
          if (current.backfill_status === "failed") {
            setBackfillMessage(`回填失败: ${current.backfill_error ?? "unknown error"}`);
          } else {
            setBackfillMessage(
              `回填完成 · ${current.linked_news_count} 关联新闻 · ${current.timeline_event_count} 事件`,
            );
          }
          await loadProduct();
          return;
        }
      } catch (caught) {
        setBackfillMessage(caught instanceof Error ? caught.message : "回填失败");
      } finally {
        pollingRef.current = false;
        setBackfilling(false);
      }
    },
    // loadProduct is stable within this component instance for a given slug
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [slug],
  );

  // Auto-start polling when the detail loads already in "running" state
  // (e.g. user was just redirected here after creating a new product and
  // the backend kicked off async backfill). Guarded by pollingRef so we
  // don't duplicate when handleBackfill is also active.
  useEffect(() => {
    if (!detail) return;
    if (detail.backfill_status !== "running") return;
    if (pollingRef.current) return;
    const startTs = detail.backfill_started_at
      ? Date.parse(detail.backfill_started_at)
      : Date.now();
    const initialElapsed = Math.floor((Date.now() - startTs) / 60000);
    setBackfillMessage(`正在回填… (已运行 ${initialElapsed} 分钟)`);
    void pollBackfillStatus(detail.slug, startTs);
  }, [detail, pollBackfillStatus]);

  async function handleBackfill() {
    if (!detail) return;
    if (pollingRef.current) {
      // Already polling (likely from auto-start); just surface a message.
      setBackfillMessage("回填已在进行中，继续监控进度…");
      return;
    }
    setBackfillMessage("正在回填… (已运行 0 分钟)");
    try {
      const response = await fetch(`${API_BASE_PATH}/products/${detail.id}/backfill`, {
        method: "POST",
      });
      if (response.status === 409) {
        setBackfillMessage("回填已在进行中，继续监控进度…");
      } else if (!response.ok) {
        throw new Error("回填失败: 无法启动任务");
      }
      await pollBackfillStatus(detail.slug, Date.now());
    } catch (caught) {
      setBackfillMessage(caught instanceof Error ? caught.message : "回填失败");
      setBackfilling(false);
    }
  }

  const timelineItems = useMemo(() => timeline?.items ?? [], [timeline]);
  const isLoading = state === "loading" || state === "idle";

  if (isLoading) {
    return (
      <main className="min-h-screen bg-apple-gray dark:bg-apple-black">
        <GlassNav title="Loading…" />
        <div className="mx-auto grid w-full max-w-[980px] gap-4 px-4 py-16">
          <div className="h-36 animate-pulse rounded-2xl bg-[#ededf2] dark:bg-apple-darkSurface1" />
          <div className="h-72 animate-pulse rounded-2xl bg-[#ededf2] dark:bg-apple-darkSurface1" />
        </div>
      </main>
    );
  }

  if (state === "error" || !detail || !timeline) {
    return (
      <main className="min-h-screen bg-apple-gray text-apple-text dark:bg-apple-black dark:text-white">
        <GlassNav title="Products" />
        <div className="mx-auto max-w-[980px] px-4 py-20 text-center">
          <p className="text-sm text-[#ff3b30]">{error || "Failed to load product timeline."}</p>
          <div className="mt-6">
            <Link
              className="text-apple-link hover:underline dark:text-apple-linkDark"
              href="/products"
            >
              ← Back to products
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-apple-gray text-apple-text dark:bg-apple-black dark:text-white">
      <GlassNav title={detail.display_name} />

      {/* Hero */}
      <section className="bg-apple-black text-white">
        <div className="mx-auto w-full max-w-[980px] px-4 py-20">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-white/55">
            <Link
              className="text-apple-linkDark hover:underline"
              href="/products"
            >
              Products
            </Link>
            <span className="text-white/30">/</span>
            <span>{detail.slug}</span>
          </div>
          <h1 className="mt-4 font-display text-[40px] font-semibold leading-[1.07] tracking-tight md:text-[48px] lg:text-[56px]">
            {detail.display_name}
          </h1>
          <p className="mt-4 text-[19px] font-light leading-[1.42] text-white/75">
            {detail.company_name || "未设置公司"}
            {detail.modality ? <span className="text-white/50"> · {detail.modality}</span> : null}
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button
              variant="outline"
              className="!text-apple-linkDark !border-white/25 hover:!bg-white/10"
              disabled={backfilling}
              onClick={handleBackfill}
              type="button"
            >
              {backfilling ? "正在回填…" : "运行回填"}
            </Button>
            <p className="text-[12px] text-white/55">
              最近回填 {detail.last_backfill_at ? formatDateTime(detail.last_backfill_at) : "尚未回填"}
            </p>
          </div>

          {backfillMessage ? (
            <p className="mt-4 inline-flex items-center gap-2 rounded-pill bg-white/10 px-3.5 py-1.5 text-[12px] text-white/85">
              {backfilling ? (
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-apple-linkDark" />
              ) : null}
              {backfillMessage}
            </p>
          ) : null}
        </div>
      </section>

      {/* Content */}
      <section className="bg-apple-gray dark:bg-apple-black">
        <div className="mx-auto grid w-full max-w-[980px] gap-8 px-4 py-16 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Card>
            <CardHeader>
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-apple-text/55 dark:text-white/50">
                  Milestones
                </p>
                <h2 className="font-display text-[21px] font-semibold tracking-tight">
                  时间线 <span className="text-apple-text/50 dark:text-white/45 text-[15px] font-normal">Timeline</span>
                </h2>
                <p className="text-[13px] leading-[1.4] text-apple-text/60 dark:text-white/55">
                  Structured milestones extracted from linked product news.
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {timelineItems.length === 0 ? (
                <p className="text-sm text-apple-text/60 dark:text-white/55">
                  暂无里程碑事件，请点击上方「运行回填」从关联新闻中提取临床与监管事件。
                </p>
              ) : (
                <ol className="relative space-y-6 border-l border-black/10 pl-6 dark:border-white/10">
                  {timelineItems.map((item) => (
                    <TimelineItem key={item.id} item={item} />
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          <aside className="space-y-5">
            <Card>
              <CardHeader>
                <div className="space-y-1">
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-apple-text/55 dark:text-white/50">
                    Profile
                  </p>
                  <h2 className="font-display text-[19px] font-semibold tracking-tight">
                    Details
                  </h2>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-[13px]">
                <StatRow label="时间线事件" value={String(detail.timeline_event_count)} />
                <StatRow label="关联新闻" value={String(detail.linked_news_count)} />
                <div className="flex items-center justify-between gap-3 rounded-md bg-[#ededf2] px-3 py-2 dark:bg-apple-darkSurface1">
                  <span className="text-apple-text/60 dark:text-white/55">状态</span>
                  {detail.status === "active" ? (
                    <Badge variant="default" className="bg-[#34c759] text-white">✓ 活跃</Badge>
                  ) : (
                    <Badge variant="secondary">✗ 已归档</Badge>
                  )}
                </div>
                <TagList label="Aliases" items={detail.aliases} />
                <TagList label="Indications" items={detail.indications} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="space-y-1">
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-apple-text/55 dark:text-white/50">
                    Evidence
                  </p>
                  <h2 className="font-display text-[19px] font-semibold tracking-tight">
                    关联新闻 <span className="text-apple-text/50 dark:text-white/45 text-[13px] font-normal">Linked news</span>
                  </h2>
                </div>
              </CardHeader>
              <CardContent>
                {detail.linked_news.length === 0 ? (
                  <p className="text-sm text-apple-text/60 dark:text-white/55">
                    暂无关联新闻
                  </p>
                ) : (
                  <ul className="space-y-3">
                    {detail.linked_news.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-md bg-[#ededf2] p-3 dark:bg-apple-darkSurface1"
                      >
                        <a
                          className="text-[14px] font-medium leading-[1.35] text-apple-text hover:text-apple-link dark:text-white dark:hover:text-apple-linkDark"
                          href={item.canonical_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {item.title}
                        </a>
                        <p className="mt-1.5 text-[11px] text-apple-text/55 dark:text-white/45">
                          {item.source_name} · {formatDateTime(item.published_at)}
                        </p>
                        {item.short_summary ? (
                          <p className="mt-2 text-[13px] leading-[1.45] text-apple-text/70 dark:text-white/65">
                            {item.short_summary}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </aside>
        </div>
      </section>

      <footer className="bg-apple-black py-12 text-center text-[12px] text-white/55">
        <div className="mx-auto max-w-[980px] px-4">
          Biomed / Cell Therapy Daily · Product timeline
        </div>
      </footer>
    </main>
  );
}

function GlassNav({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-[20px] backdrop-saturate-150 text-white">
      <div className="mx-auto flex h-12 w-full max-w-[980px] items-center justify-between gap-4 px-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link className="font-display text-[17px] font-semibold tracking-tight" href="/">
            Biomed / Cell Therapy Daily
          </Link>
          <span className="hidden truncate text-xs text-white/50 sm:inline">/ {title}</span>
        </div>
        <div className="hidden sm:block">
          <TopNav />
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

function TimelineItem({ item }: { item: ProductTimelineEvent }) {
  return (
    <li className="relative">
      <span className="absolute -left-[33px] top-1.5 h-3 w-3 rounded-full bg-apple-blue ring-4 ring-white dark:ring-apple-darkSurface3" />
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[13px] font-semibold text-apple-blue">
            {formatEventDate(item.event_date, item.event_date_precision)}
          </p>
          <span className="text-[11px] uppercase tracking-[0.14em] text-apple-text/50 dark:text-white/45">
            {item.milestone_type}
          </span>
        </div>
        <h3 className="font-display text-[17px] font-semibold leading-[1.3] tracking-tight">
          {item.headline}
        </h3>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="default" className="text-[11px]">{item.milestone_label}</Badge>
          {item.phase_label ? (
            <Badge variant="secondary" className="text-[11px]">{item.phase_label}</Badge>
          ) : null}
          {item.indication ? (
            <Badge variant="outline" className="text-[11px]">{item.indication}</Badge>
          ) : null}
        </div>
        {item.event_summary ? (
          <p className="text-[14px] leading-[1.5] text-apple-text/75 dark:text-white/70">
            {item.event_summary}
          </p>
        ) : null}
        {item.evidence_urls.length > 0 ? (
          <div className="flex flex-wrap gap-3 pt-1">
            {item.evidence_urls.slice(0, 3).map((url, index) => {
              let label: string;
              try {
                label = `${new URL(url).hostname} ↗`;
              } catch {
                label = `Source ${index + 1}`;
              }
              return (
                <a
                  key={url}
                  className="text-[12px] text-apple-link hover:underline dark:text-apple-linkDark"
                  href={url}
                  rel="noreferrer"
                  target="_blank"
                >
                  {label}
                </a>
              );
            })}
          </div>
        ) : null}
      </div>
    </li>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-[#ededf2] px-3 py-2 dark:bg-apple-darkSurface1">
      <span className="text-apple-text/60 dark:text-white/55">{label}</span>
      <span className="font-medium text-apple-text dark:text-white">{value}</span>
    </div>
  );
}

function TagList({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-apple-text/55 dark:text-white/45">
        {label}
      </p>
      {items.length === 0 ? (
        <p className="text-[12px] text-apple-text/45 dark:text-white/40">None</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <Badge key={item} variant="secondary" className="text-[11px]">
              {item}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
