import { type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  type AnalysisResult,
  type KeywordCount,
  type Quote,
  analysisUrl,
  reportUrl,
} from "../api";
import { type ChartTheme, NEG, NEU, POS, chartTheme } from "../charts";

export default function ReportDashboard({
  result,
  jobId,
  isDark,
}: {
  result: AnalysisResult;
  jobId: string;
  isDark: boolean;
}) {
  if (result.totals.comments === 0) {
    return (
      <div className="card animate-fade-in-up text-sm text-zinc-500 dark:text-zinc-400">
        No comments were collected for <strong>{result.product}</strong>. Try a different platform
        or a higher results-per-query.
      </div>
    );
  }

  const ct = chartTheme(isDark);
  const trendDays = result.trends.by_day ?? [];

  return (
    <div className="space-y-5">
      <Header result={result} jobId={jobId} />
      {result.summary && (
        <Section title="Executive summary">
          <div className="prose prose-sm max-w-none text-zinc-700 dark:prose-invert dark:text-zinc-300">
            <ReactMarkdown>{result.summary}</ReactMarkdown>
          </div>
        </Section>
      )}

      <StatTiles result={result} />

      <div className="grid gap-5 lg:grid-cols-2">
        <SentimentCard result={result} ct={ct} />
        <KeywordsCard result={result} ct={ct} />
      </div>

      {trendDays.length >= 2 ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <Section title="Volume over time">
            <TrendChart days={trendDays} ct={ct} />
          </Section>
          <Section title="Representative quotes">
            <Quotes result={result} />
          </Section>
        </div>
      ) : (
        <Section title="Representative quotes">
          <Quotes result={result} />
        </Section>
      )}

      {result.suggestions.length > 0 && (
        <Section title="Improvement suggestions">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
            {result.suggestions.map((s, i) => (
              <li key={i}>
                <ReactMarkdown components={{ p: ({ children }) => <span>{children}</span> }}>
                  {s}
                </ReactMarkdown>
              </li>
            ))}
          </ol>
        </Section>
      )}

      <p className="px-1 text-xs text-zinc-400 dark:text-zinc-500">
        Data is from DuckDuckGo search snippets — directional, not full comment threads
        (author/likes may be missing).
      </p>
    </div>
  );
}

function Header({ result, jobId }: { result: AnalysisResult; jobId: string }) {
  return (
    <div className="card flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{result.product}</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {result.totals.comments} comments · {result.platforms.join(", ")} ·{" "}
          {new Date(result.generated_at).toLocaleString()}
        </p>
      </div>
      <div className="flex gap-2">
        <a className="btn-download" href={reportUrl(jobId)} download>
          ↓ report.md
        </a>
        <a className="btn-download" href={analysisUrl(jobId)} download>
          ↓ analysis.json
        </a>
      </div>
    </div>
  );
}

function StatTiles({ result }: { result: AnalysisResult }) {
  const s = result.sentiment;
  const total = s.count || 1;
  const pct = (n: number) => `${Math.round((n / total) * 100)}%`;
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <div className="stat-tile">
        <TileLabel>Mean sentiment</TileLabel>
        <TileValue>
          {s.mean >= 0 ? "+" : ""}
          {s.mean.toFixed(3)}
        </TileValue>
        <ShareBar dist={s.distribution} />
      </div>
      <div className="stat-tile">
        <TileLabel>Comments analyzed</TileLabel>
        <TileValue>{s.count}</TileValue>
      </div>
      <div className="stat-tile">
        <TileLabel>Positive share</TileLabel>
        <TileValue>{pct(s.distribution.positive)}</TileValue>
      </div>
    </div>
  );
}

const TileLabel = ({ children }: { children: ReactNode }) => (
  <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">{children}</div>
);
const TileValue = ({ children }: { children: ReactNode }) => (
  <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
    {children}
  </div>
);

function ShareBar({ dist }: { dist: { positive: number; neutral: number; negative: number } }) {
  const total = dist.positive + dist.neutral + dist.negative || 1;
  const seg = (n: number, color: string) =>
    n > 0 ? <div style={{ width: `${(n / total) * 100}%`, background: color }} /> : null;
  return (
    <div className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
      {seg(dist.positive, POS)}
      {seg(dist.neutral, NEU)}
      {seg(dist.negative, NEG)}
    </div>
  );
}

function SentimentCard({ result, ct }: { result: AnalysisResult; ct: ChartTheme }) {
  const s = result.sentiment;
  const dist = [
    { name: "Positive", value: s.distribution.positive, fill: POS },
    { name: "Neutral", value: s.distribution.neutral, fill: NEU },
    { name: "Negative", value: s.distribution.negative, fill: NEG },
  ];
  const byPlatform = Object.entries(s.by_platform).sort((a, b) => b[1].count - a[1].count);
  return (
    <Section title="Sentiment">
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dist} margin={{ top: 8 }}>
            <XAxis dataKey="name" tick={{ fill: ct.tick, fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} tick={{ fill: ct.tick, fontSize: 12 }} tickLine={false} axisLine={false} width={28} />
            <Tooltip
              contentStyle={ct.tooltipContentStyle}
              itemStyle={ct.tooltipItemStyle}
              cursor={ct.tooltipCursor}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {dist.map((d) => (
                <Cell key={d.name} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {byPlatform.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-zinc-400">
              <th className="py-1 font-medium">Platform</th>
              <th className="py-1 text-right font-medium">Comments</th>
              <th className="py-1 text-right font-medium">Mean</th>
            </tr>
          </thead>
          <tbody>
            {byPlatform.map(([name, st]) => (
              <tr key={name} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1.5 capitalize text-zinc-700 dark:text-zinc-300">{name}</td>
                <td className="py-1.5 text-right tabular-nums">{st.count}</td>
                <td
                  className="py-1.5 text-right tabular-nums font-medium"
                  style={{ color: st.mean >= 0 ? POS : NEG }}
                >
                  {st.mean >= 0 ? "+" : ""}
                  {st.mean.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function KeywordsCard({ result, ct }: { result: AnalysisResult; ct: ChartTheme }) {
  const top = result.top_keywords.slice(0, 10).map(([word, count]) => ({ word, count }));
  return (
    <Section title="Top keywords">
      <div className="h-60">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={top} layout="vertical" margin={{ left: 8 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fill: ct.tick, fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="word" width={88} tick={{ fill: ct.tick, fontSize: 12 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={ct.tooltipContentStyle}
              itemStyle={ct.tooltipItemStyle}
              cursor={ct.tooltipCursor}
            />
            <Bar dataKey="count" fill={ct.bar} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 space-y-3">
        <KeywordChips title="In positive comments" items={result.keywords_by_sentiment.positive.keywords} dot={POS} />
        <KeywordChips title="In negative comments" items={result.keywords_by_sentiment.negative.keywords} dot={NEG} />
      </div>
    </Section>
  );
}

function KeywordChips({ title, items, dot }: { title: string; items: KeywordCount[]; dot: string }) {
  return (
    <div>
      <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-zinc-400">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: dot }} />
        {title}
      </h4>
      <div className="flex flex-wrap gap-1.5">
        {items.length === 0 && <span className="text-sm text-zinc-400">none</span>}
        {items.slice(0, 12).map(([word, count]) => (
          <span
            key={word}
            className="rounded-md border border-zinc-200 bg-white px-2 py-0.5 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          >
            {word} · {count}
          </span>
        ))}
      </div>
    </div>
  );
}

function TrendChart({ days, ct }: { days: AnalysisResult["trends"]["by_day"]; ct: ChartTheme }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={days}>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} vertical={false} />
          <XAxis dataKey="date" tick={{ fill: ct.tick, fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: ct.tick, fontSize: 12 }} tickLine={false} axisLine={false} width={28} />
          <Tooltip
            contentStyle={ct.tooltipContentStyle}
            itemStyle={ct.tooltipItemStyle}
            cursor={ct.tooltipCursor}
          />
          <Line type="monotone" dataKey="count" stroke={ct.bar} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Quotes({ result }: { result: AnalysisResult }) {
  const { positive, negative } = result.representative;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <QuoteColumn label="Positive" quotes={positive} accent={POS} />
      <QuoteColumn label="Negative" quotes={negative} accent={NEG} />
    </div>
  );
}

function QuoteColumn({ label, quotes, accent }: { label: string; quotes: Quote[]; accent: string }) {
  return (
    <div className="space-y-3">
      <h4 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        <span className="h-2 w-2 rounded-full" style={{ background: accent }} />
        {label}
      </h4>
      {quotes.length === 0 && <p className="text-sm text-zinc-400">none</p>}
      {quotes.map((q, i) => (
        <blockquote
          key={i}
          className="rounded-lg border border-zinc-200 border-l-2 bg-white p-3 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300"
          style={{ borderLeftColor: accent }}
        >
          <p className="line-clamp-4">{q.text}</p>
          <footer className="mt-1.5 text-xs text-zinc-400">
            <span className="capitalize">{q.source}</span>
            {q.author && ` · ${q.author}`}
            {q.likes != null && ` · ${q.likes} likes`}
            {q.url && (
              <>
                {" · "}
                <a
                  className="text-zinc-500 underline underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100"
                  href={q.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  source
                </a>
              </>
            )}
          </footer>
        </blockquote>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {title}
      </h3>
      {children}
    </section>
  );
}
