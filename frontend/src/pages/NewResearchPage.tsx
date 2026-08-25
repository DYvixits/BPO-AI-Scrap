import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { createResearch } from "@/features/research/api";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api";
import type { ResearchMode } from "@/types/api";

const MODES: { value: ResearchMode; label: string; description: string }[] = [
  { value: "quick", label: "Quick", description: "Fastest — a handful of top sources" },
  { value: "balanced", label: "Balanced", description: "Good default speed/coverage tradeoff" },
  { value: "deep", label: "Deep", description: "Wider coverage, more sources crawled" },
  { value: "verified", label: "Verified", description: "Prioritizes corroborated sources" },
  { value: "investigation", label: "Investigation", description: "Maximum depth and source count" },
];

const EXAMPLES = [
  "Find African fintech companies founded after 2020 with funding above $1M",
  "Compare the top 5 headless CMS platforms for a mid-size SaaS company",
  "Find recent, verified news about a company's leadership changes",
  "Analyze the electric-bike market in Southeast Asia",
];

export function NewResearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ResearchMode>("balanced");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleStart() {
    if (query.trim().length < 3) {
      setError("Tell us a bit more about what you're looking for.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const job = await createResearch({ query: query.trim(), mode });
      navigate(`/research/${job.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start research. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 py-16">
      <h1 className="text-center text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        What do you want to discover?
      </h1>
      <p className="mt-3 text-center text-muted-foreground">
        Describe your research goal in plain language. We&apos;ll plan the research, crawl the web, and bring
        back evidence-backed results.
      </p>

      <div className="mt-8 w-full">
        <Textarea
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find African fintech companies founded after 2020 with funding above $1M..."
          className="min-h-32 text-base"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleStart();
          }}
        />

        <div className="mt-4 flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              title={m.description}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                mode === m.value
                  ? "border-primary bg-accent text-accent-foreground"
                  : "border-border text-muted-foreground hover:bg-accent/50",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

        <Button size="lg" className="mt-6 w-full" onClick={handleStart} disabled={submitting}>
          {submitting ? "Starting research..." : "Start Research"}
        </Button>
      </div>

      <div className="mt-10 w-full">
        <p className="mb-3 text-center text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Try
        </p>
        <div className="flex flex-col gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuery(example)}
              className="rounded-md border border-border px-4 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/50 hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
