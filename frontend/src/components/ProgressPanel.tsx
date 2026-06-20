import { useEffect, useRef, useState } from "react";

interface Props {
  lines: string[];
  status: "running" | "error";
  error?: string | null;
}

type StepState = "pending" | "active" | "done" | "error";

export default function ProgressPanel({ lines, status, error }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [showLog, setShowLog] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (status !== "running") return;
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [status]);

  useEffect(() => {
    if (showLog) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, showLog]);

  // Derive the current stage + a live comment tally from the streamed lines.
  const insightsStarted = lines.some((l) => /insight/i.test(l));
  let tally: number | null = null;
  for (const l of lines) {
    const m = l.match(/total (\d+)/) || l.match(/loaded (\d+)/);
    if (m) tally = Math.max(tally ?? 0, Number(m[1]));
  }
  const current = lines.length ? lines[lines.length - 1] : "Starting…";

  const steps: { label: string; state: StepState }[] = [
    {
      label: "Gathering comments",
      state: status === "error" && !insightsStarted ? "error" : insightsStarted ? "done" : "active",
    },
    {
      label: "Generating insights",
      state:
        status === "error" && insightsStarted
          ? "error"
          : insightsStarted
            ? "active"
            : "pending",
    },
  ];

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="card">
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {status === "error" ? "Analysis failed" : "Running analysis"}
        </span>
        <span className="flex items-center gap-2 text-xs tabular-nums text-zinc-400">
          {tally != null && (
            <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">
              {tally} comments
            </span>
          )}
          {mm}:{ss}
        </span>
      </div>

      <ol className="space-y-3">
        {steps.map((s) => (
          <li key={s.label} className="flex items-center gap-3">
            <StepDot state={s.state} />
            <span
              className={
                s.state === "pending"
                  ? "text-sm text-zinc-400"
                  : s.state === "error"
                    ? "text-sm font-medium text-rose-600 dark:text-rose-400"
                    : "text-sm font-medium text-zinc-900 dark:text-zinc-100"
              }
            >
              {s.label}
            </span>
          </li>
        ))}
      </ol>

      {status === "running" && (
        <div className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div className="h-full w-1/4 animate-indeterminate rounded-full bg-zinc-900 dark:bg-zinc-100" />
        </div>
      )}

      <p className="mt-3 truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">{current}</p>
      {error && <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p>}

      <button
        type="button"
        onClick={() => setShowLog((v) => !v)}
        className="mt-3 text-xs text-zinc-400 transition hover:text-zinc-700 dark:hover:text-zinc-200"
      >
        {showLog ? "▾" : "▸"} Details
      </button>
      {showLog && (
        <div className="mt-2 max-h-56 overflow-auto rounded-lg bg-zinc-50 p-3 font-mono text-xs leading-relaxed text-zinc-500 ring-1 ring-inset ring-zinc-200 dark:bg-zinc-950 dark:text-zinc-400 dark:ring-zinc-800">
          {lines.length === 0 ? (
            <span className="text-zinc-400">starting…</span>
          ) : (
            lines.map((l, i) => <div key={i}>{l}</div>)
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
}

function StepDot({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900">
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3">
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-zinc-900 dark:bg-zinc-100" />
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-rose-600 text-white">
        <span className="text-xs">!</span>
      </span>
    );
  }
  return (
    <span className="grid h-5 w-5 shrink-0 place-items-center">
      <span className="h-2.5 w-2.5 rounded-full border border-zinc-300 dark:border-zinc-600" />
    </span>
  );
}
