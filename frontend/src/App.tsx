import { useEffect, useRef, useState } from "react";
import {
  type AnalysisResult,
  type CreateRequest,
  type MetaResponse,
  createAnalysis,
  getJob,
  getMeta,
  openProgressStream,
} from "./api";
import AnalysisForm from "./components/AnalysisForm";
import ProgressPanel from "./components/ProgressPanel";
import ReportDashboard from "./components/ReportDashboard";
import ThemeToggle from "./components/ThemeToggle";
import VoiceBackground from "./components/VoiceBackground";
import { useTheme } from "./hooks/useTheme";

type Phase = "idle" | "running" | "done" | "error";

export default function App() {
  const { isDark, toggle } = useTheme();
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<string[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeStream = useRef<(() => void) | null>(null);
  const flowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch((e) => setMetaError(String(e)));
    return () => closeStream.current?.();
  }, []);

  // Once a run starts (and again when the report lands), scroll down to follow the workflow.
  useEffect(() => {
    if (phase === "running" || phase === "done") {
      const id = requestAnimationFrame(() =>
        flowRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
      return () => cancelAnimationFrame(id);
    }
  }, [phase]);

  const start = async (req: CreateRequest) => {
    setPhase("running");
    setProgress([]);
    setResult(null);
    setError(null);
    try {
      const id = await createAnalysis(req);
      setJobId(id);
      closeStream.current = openProgressStream(id, async (e) => {
        if (e.type === "progress") {
          setProgress((p) => [...p, e.line]);
        } else if (e.type === "done") {
          closeStream.current?.();
          const job = await getJob(id);
          setResult(job.result);
          setPhase("done");
        } else if (e.type === "error") {
          closeStream.current?.();
          setError(e.error);
          setPhase("error");
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  };

  const reset = () => {
    closeStream.current?.();
    setPhase("idle");
    setResult(null);
    setProgress([]);
    setError(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="min-h-screen">
      {phase === "idle" && <VoiceBackground />}
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <span className="text-sm font-medium tracking-tight text-zinc-900 dark:text-zinc-100">
            Voice of Customer
          </span>
          <ThemeToggle isDark={isDark} onToggle={toggle} />
        </div>
      </header>

      <main className="mx-auto px-4 pb-24">
        <section
          className={`mx-auto max-w-3xl ${
            phase === "idle"
              ? "flex min-h-[calc(100vh-3.5rem)] flex-col justify-center"
              : "pt-10"
          }`}
        >
          <h1 className="text-3xl font-medium leading-tight tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Hear what customers really think.
          </h1>

          {metaError && (
            <div className="card mt-6 text-sm text-rose-600 dark:text-rose-400">
              Could not reach the API ({metaError}). Is the backend running?
            </div>
          )}

          {meta && (
            <div className="card mt-6 animate-fade-in-up">
              <AnalysisForm meta={meta} disabled={phase === "running"} onSubmit={start} />
              {phase !== "idle" && (
                <button
                  className="mt-4 text-sm text-zinc-500 underline-offset-2 transition hover:text-zinc-900 hover:underline dark:hover:text-zinc-100"
                  onClick={reset}
                >
                  ← New analysis
                </button>
              )}
            </div>
          )}
        </section>

        {meta && phase !== "idle" && (
          <section ref={flowRef} className="mx-auto mt-8 max-w-5xl scroll-mt-20 animate-fade-in-up">
            {(phase === "running" || phase === "error") && (
              <ProgressPanel
                lines={progress}
                status={phase === "error" ? "error" : "running"}
                error={error}
              />
            )}
            {phase === "done" && result && jobId && (
              <ReportDashboard result={result} jobId={jobId} isDark={isDark} />
            )}
          </section>
        )}
      </main>
    </div>
  );
}
