"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { TopNav } from "@/components/top-nav";

import type {
  CorporateCompanyEntry,
  CorporateDynamicsResponse,
  CorporateSignal,
  NewsItem,
} from "@/lib/types";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH || "/api";

type TabKey = "all" | CorporateSignal;

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "layoffs", label: "裁员 · 重组" },
  { key: "new_pipeline", label: "新管线 · IND" },
  { key: "financing", label: "融资 · 估值" },
];

const BUCKET_LABEL: Record<CorporateSignal, string> = {
  layoffs: "裁员 · 重组",
  new_pipeline: "新管线 · IND",
  financing: "融资 · 估值",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function NewsRow({ item, bucket }: { item: NewsItem; bucket: CorporateSignal }) {
  return (
    <li className="rounded-xl bg-black/20 p-3 transition-colors hover:bg-black/30">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-white/55">
        <span className="rounded-pill bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/80">
          {BUCKET_LABEL[bucket]}
        </span>
        <span>{formatDate(item.published_at)}</span>
        <span className="text-white/40">·</span>
        <span>{item.source_name}</span>
      </div>
      <Link
        className="mt-1 block text-sm font-medium text-white hover:text-apple-blue"
        href={item.canonical_url}
        rel="noopener noreferrer"
        target="_blank"
      >
        {item.title}
      </Link>
      {item.short_summary ? (
        <p className="mt-1 line-clamp-2 text-xs text-white/65">{item.short_summary}</p>
      ) : null}
    </li>
  );
}

function CompanyCard({ entry, tab }: { entry: CorporateCompanyEntry; tab: TabKey }) {
  const buckets: CorporateSignal[] =
    tab === "all" ? ["layoffs", "new_pipeline", "financing"] : [tab];
  const sections = buckets
    .map((b) => ({ bucket: b, items: entry.signals[b] || [] }))
    .filter((s) => s.items.length > 0);

  if (sections.length === 0) return null;

  return (
    <article className="flex flex-col gap-4 rounded-2xl bg-apple-darkSurface1 p-5 shadow-apple">
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h3 className="font-display text-xl font-semibold tracking-tight text-white">
            {entry.chinese_name || entry.name}
          </h3>
          <p className="text-xs text-white/55">{entry.name}</p>
        </div>
        <span className="text-[10px] text-white/40">
          更新 {formatDate(entry.last_updated_at)}
        </span>
      </header>
      <div className="flex flex-col gap-3">
        {sections.map((section) => (
          <div key={section.bucket}>
            <h4 className="mb-2 text-[11px] uppercase tracking-wider text-white/50">
              {BUCKET_LABEL[section.bucket]} · {section.items.length}
            </h4>
            <ul className="flex flex-col gap-2">
              {section.items.slice(0, 4).map((item) => (
                <NewsRow key={`${section.bucket}-${item.id}`} item={item} bucket={section.bucket} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </article>
  );
}

export function CorporateDynamics() {
  const [data, setData] = useState<CorporateDynamicsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");
  const [companyFilter, setCompanyFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (tab !== "all") params.set("signal", tab);
        const response = await fetch(
          `${API_BASE_PATH}/corporate-dynamics${params.toString() ? `?${params}` : ""}`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as CorporateDynamicsResponse;
        if (!cancelled) setData(payload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [tab]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const needle = companyFilter.trim().toLowerCase();
    if (!needle) return data.companies;
    return data.companies.filter(
      (c) =>
        c.name.toLowerCase().includes(needle) ||
        (c.chinese_name || "").toLowerCase().includes(needle),
    );
  }, [data, companyFilter]);

  return (
    <main className="min-h-screen bg-apple-black text-white">
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
          <div />
        </div>
      </header>

      <section className="mx-auto w-full max-w-[980px] px-4 pb-24 pt-12">
        <div className="mb-8">
          <h1 className="font-display text-4xl font-semibold tracking-tight sm:text-5xl">企业动态</h1>
          <p className="mt-2 text-sm text-white/65">
            细胞疗法赛道主流公司的裁员、新管线、融资信号一览
          </p>
        </div>

        <div className="mb-6 flex flex-wrap items-center gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-pill px-4 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key
                  ? "bg-white text-apple-black"
                  : "bg-apple-darkSurface1 text-white/75 hover:bg-white/15"
              }`}
            >
              {t.label}
            </button>
          ))}
          <input
            type="search"
            value={companyFilter}
            onChange={(e) => setCompanyFilter(e.target.value)}
            placeholder="公司搜索 (Novartis / 诺华)"
            className="ml-auto min-w-[200px] flex-1 rounded-pill bg-apple-darkSurface1 px-4 py-1.5 text-xs text-white placeholder:text-white/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue"
          />
        </div>

        {loading ? (
          <p className="text-sm text-white/50">加载中…</p>
        ) : error ? (
          <p className="text-sm text-red-400">加载失败: {error}</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl bg-apple-darkSurface1 p-10 text-center shadow-apple">
            <p className="text-sm text-white/60">暂无数据</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {filtered.map((entry) => (
              <CompanyCard key={entry.name} entry={entry} tab={tab} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
