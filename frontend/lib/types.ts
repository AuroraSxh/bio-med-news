export type CategoriesResponse = {
  categories: string[];
};

export type NewsItem = {
  id: number;
  title: string;
  canonical_url: string;
  source_name: string;
  published_at: string;
  category: string;
  short_summary: string;
  image_url: string | null;
  language: string | null;
  entities: string[] | null;
  importance_score: number | null;
  relevance_to_cell_therapy: number | null;
};

export type NewsListResponse = {
  items: NewsItem[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
  filters: {
    category: string | null;
    date: string | null;
    q: string | null;
    sort: string;
  };
  last_updated_at: string;
  category_counts: Record<string, number>;
};

export type TopEvent = {
  title: string;
  category: string;
  canonical_url: string;
  source_name: string | null;
  published_at: string | null;
  short_summary: string | null;
};

export type TodaySummaryResponse = {
  available: boolean;
  summary_date: string;
  daily_summary: string | null;
  top_events: TopEvent[];
  trend_signal: string | null;
  category_counts: Record<string, number>;
  category_summaries: Record<string, string>;
  model_name: string | null;
  generated_at: string | null;
};

export type ModelInfo = {
  id: string;
  label: string;
  type: string;
  description: string;
};

export type ModelsResponse = {
  models: ModelInfo[];
  current: string;
};

export type ProductNewsItem = {
  id: number;
  title: string;
  canonical_url: string;
  source_name: string;
  published_at: string;
  category: string;
  short_summary: string;
  match_source: string;
  match_confidence: number | null;
};

export type ProductTimelineEvent = {
  id: number;
  event_date: string;
  event_date_precision: string;
  milestone_type: string;
  milestone_label: string;
  phase_label: string | null;
  headline: string;
  event_summary: string;
  indication: string | null;
  region: string | null;
  confidence: number | null;
  evidence_news_item_ids: number[];
  evidence_urls: string[];
};

export type BackfillStatus = "idle" | "running" | "done" | "failed";

export type TrackedProductListItem = {
  id: number;
  slug: string;
  display_name: string;
  company_name: string | null;
  aliases: string[];
  indications: string[];
  modality: string | null;
  status: string;
  timeline_event_count: number;
  linked_news_count: number;
  last_backfill_at: string | null;
  backfill_status: BackfillStatus;
  backfill_started_at: string | null;
  backfill_error: string | null;
  updated_at: string;
};

export type TrackedProductDetail = TrackedProductListItem & {
  latest_timeline_event: ProductTimelineEvent | null;
  linked_news: ProductNewsItem[];
};

export type ProductListResponse = {
  items: TrackedProductListItem[];
};

export type ProductTimelineResponse = {
  product: TrackedProductListItem;
  items: ProductTimelineEvent[];
};

export type ProductBackfillResponse = {
  accepted: boolean;
  product_id: number;
  product_slug: string;
  fetched_candidates: number;
  linked_news_count: number;
  created_timeline_events: number;
  updated_at: string;
};

export type ProductCreateRequest = {
  display_name: string;
  company_name: string | null;
  aliases: string[];
  indications: string[];
  modality: string | null;
};

export type ProductListItem = TrackedProductListItem;

export type ProductDetailResponse = TrackedProductDetail;

export type CorporateSignal = "layoffs" | "new_pipeline" | "financing";

export type CorporateDynamicsBuckets = {
  layoffs: NewsItem[];
  new_pipeline: NewsItem[];
  financing: NewsItem[];
};

export type CorporateCompanyEntry = {
  name: string;
  chinese_name: string;
  signals: CorporateDynamicsBuckets;
  last_updated_at: string | null;
};

export type CorporateDynamicsResponse = {
  companies: CorporateCompanyEntry[];
  total_companies: number;
};
