// Typed client for the VoC analyzer API. Interfaces mirror the backend `analysis` dict.

export type Source = "youtube" | "reddit" | "tiktok" | "instagram" | "x";
export type KeywordCount = [string, number];

export interface SentimentByPlatform {
  count: number;
  mean: number;
}
export interface Sentiment {
  count: number;
  mean: number;
  distribution: { positive: number; neutral: number; negative: number };
  by_platform: Record<string, SentimentByPlatform>;
}
export interface KeywordsBucket {
  keywords: KeywordCount[];
  phrases: KeywordCount[];
}
export interface KeywordsBySentiment {
  positive: KeywordsBucket;
  negative: KeywordsBucket;
}
export interface TrendDay {
  date: string;
  count: number;
  mean_sentiment: number;
}
export interface Trends {
  by_day?: TrendDay[];
  first_day?: string;
  last_day?: string;
  peak_day?: TrendDay;
}
export interface Quote {
  text: string;
  source: Source;
  author: string | null;
  likes: number | null;
  url: string;
  score: number;
}
export interface AnalysisResult {
  product: string;
  keywords: string[];
  platforms: string[];
  generated_at: string;
  totals: { comments: number; by_platform: Record<string, number> };
  sentiment: Sentiment;
  top_keywords: KeywordCount[];
  top_phrases: KeywordCount[];
  keywords_by_sentiment: KeywordsBySentiment;
  trends: Trends;
  representative: { positive: Quote[]; negative: Quote[] };
  summary: string;
  suggestions: string[];
}
export interface MetaResponse {
  platforms: string[];
  llm_enabled: boolean;
  llm_provider: string;
  models: string[];
  default_model: string;
  gather_defaults: { max_rounds: number; max_total: number; target: number };
}
export interface CreateRequest {
  product: string;
  keywords: string[];
  platforms: string[];
  limit: number;
  max_rounds?: number | null;
  use_llm: boolean;
  demo: boolean;
  model?: string | null;
}
export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
  progress: string[];
  result: AnalysisResult | null;
  rounds: number | null;
  stop_reason: string | null;
  controller: string | null;
  comment_count: number | null;
}

export type ProgressEvent =
  | { type: "progress"; line: string }
  | { type: "done" }
  | { type: "error"; error: string };

export async function getMeta(): Promise<MetaResponse> {
  const r = await fetch("/api/meta");
  if (!r.ok) throw new Error("failed to load meta");
  return r.json();
}

export async function createAnalysis(req: CreateRequest): Promise<string> {
  const r = await fetch("/api/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    let detail = `request failed (${r.status})`;
    try {
      const body = await r.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return (await r.json()).job_id as string;
}

export async function getModels(): Promise<string[]> {
  const r = await fetch("/api/models");
  if (!r.ok) throw new Error("failed to load models");
  return (await r.json()).models as string[];
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const r = await fetch(`/api/analyses/${jobId}`);
  if (!r.ok) throw new Error("failed to load job");
  return r.json();
}

// Subscribe to SSE progress. Returns a close() function.
export function openProgressStream(jobId: string, onEvent: (e: ProgressEvent) => void): () => void {
  const es = new EventSource(`/api/analyses/${jobId}/progress`);
  es.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data) as ProgressEvent);
    } catch {
      /* ignore malformed frame */
    }
  };
  es.onerror = () => es.close(); // stop auto-reconnect once the server closes the stream
  return () => es.close();
}

export const reportUrl = (jobId: string) => `/api/analyses/${jobId}/report.md`;
export const analysisUrl = (jobId: string) => `/api/analyses/${jobId}/analysis.json`;
