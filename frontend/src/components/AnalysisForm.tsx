import { useEffect, useState, type FormEvent } from "react";
import { type CreateRequest, type MetaResponse, getModels } from "../api";

interface Props {
  meta: MetaResponse;
  disabled: boolean;
  onSubmit: (req: CreateRequest) => void;
}

export default function AnalysisForm({ meta, disabled, onSubmit }: Props) {
  const [product, setProduct] = useState("");
  const [keywords, setKeywords] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(() => [...meta.platforms]);
  const [limit, setLimit] = useState(10);
  const [maxRounds, setMaxRounds] = useState(1);
  const [advanced, setAdvanced] = useState(false);
  const [model, setModel] = useState(""); // blank → use the server default
  const [allModels, setAllModels] = useState<string[]>(meta.models);
  const showModel = meta.llm_enabled; // LLM insights are always on when a provider is configured

  useEffect(() => {
    // Expand the curated list with the provider's full catalog (best-effort).
    getModels().then(setAllModels).catch(() => {});
  }, []);

  const togglePlatform = (p: string) =>
    setPlatforms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      product: product.trim(),
      keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
      platforms,
      limit,
      max_rounds: maxRounds,
      use_llm: true,
      demo: false,
      model: showModel ? model.trim() || undefined : undefined,
    });
  };

  const canSubmit = product.trim().length > 0 && platforms.length > 0;

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* Hero search row: product + inline Run */}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className="input flex-1 text-base"
          value={product}
          onChange={(e) => setProduct(e.target.value)}
          placeholder="Product to analyze — e.g. Sony WH-1000XM5"
          aria-label="Product"
        />
        <button type="submit" disabled={disabled || !canSubmit} className="btn shrink-0 px-6">
          {disabled ? "Running…" : "Run analysis →"}
        </button>
      </div>

      <input
        className="input"
        value={keywords}
        onChange={(e) => setKeywords(e.target.value)}
        placeholder="Keywords (optional, comma-separated) — battery life, comfort"
        aria-label="Keywords"
      />

      {/* Platforms */}
      <div className="flex flex-wrap gap-2">
        {meta.platforms.map((p) => {
          const on = platforms.includes(p);
          return (
            <button
              type="button"
              key={p}
              onClick={() => togglePlatform(p)}
              className={`pill ${
                on
                  ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                  : "border-zinc-300 bg-white text-zinc-600 hover:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-100"
              }`}
            >
              {p}
            </button>
          );
        })}
      </div>

      {/* Options */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl bg-zinc-50 px-4 py-3 text-sm dark:bg-zinc-800/50">
        {showModel && (
          <label className="flex items-center gap-2">
            <span className="text-zinc-500 dark:text-zinc-400">Model</span>
            <input
              list="model-options"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={`default: ${meta.default_model}`}
              className="w-60 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-sm text-zinc-700 outline-none transition focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:focus:border-zinc-300"
            />
            <datalist id="model-options">
              {allModels.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
        )}
        <label className="flex items-center gap-2">
          <span className="text-zinc-500 dark:text-zinc-400">Results/query</span>
          <input
            type="range"
            min={3}
            max={50}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="accent-zinc-900 dark:accent-zinc-100"
          />
          <span className="w-6 tabular-nums font-medium">{limit}</span>
        </label>
      </div>

      {/* Advanced */}
      <div>
        <button
          type="button"
          className="text-xs font-medium text-zinc-700 dark:text-zinc-300"
          onClick={() => setAdvanced((a) => !a)}
        >
          {advanced ? "▾" : "▸"} Advanced
        </button>
        {advanced && (
          <label className="mt-2 flex items-center gap-2 text-sm">
            <span className="text-zinc-600 dark:text-zinc-300">Max gathering rounds</span>
            <input
              type="number"
              min={1}
              max={meta.gather_defaults.max_rounds}
              value={maxRounds}
              onChange={(e) => setMaxRounds(Number(e.target.value))}
              className="input w-20"
            />
          </label>
        )}
      </div>
    </form>
  );
}
