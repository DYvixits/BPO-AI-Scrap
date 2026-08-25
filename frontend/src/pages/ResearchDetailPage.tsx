import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { describeEvent, STATUS_LABEL, statusProgressPercent } from "@/features/research/format";
import { getResearch, getResearchResults } from "@/features/research/api";
import { useResearchEvents } from "@/features/research/useResearchEvents";
import type { ResearchEvent, ResearchResult } from "@/types/api";

const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: job, isLoading } = useQuery({
    queryKey: ["research", id],
    queryFn: () => getResearch(id as string),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data && TERMINAL_STATUSES.has(query.state.data.status) ? false : 2000),
  });

  const isTerminal = job ? TERMINAL_STATUSES.has(job.status) : false;

  const { data: results } = useQuery({
    queryKey: ["research", id, "results"],
    queryFn: () => getResearchResults(id as string),
    enabled: !!id && job?.status === "completed",
  });

  const { events: liveEvents } = useResearchEvents(isTerminal ? undefined : id);

  const timeline: ResearchEvent[] = useMemo(() => {
    // Dedupe by kind+payload content, not by timestamp: the REST-fetched
    // events carry the server's created_at, while WS-received events are
    // stamped client-side on arrival — the same event can otherwise appear
    // to have two different timestamps and show up twice.
    const fromJob = job?.events ?? [];
    const seen = new Set(fromJob.map((e) => `${e.kind}:${JSON.stringify(e.payload)}`));
    const merged = [...fromJob];
    for (const e of liveEvents) {
      const key = `${e.kind}:${JSON.stringify(e.payload)}`;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(e);
      }
    }
    return merged;
  }, [job?.events, liveEvents]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-4 h-4 w-full" />
        <Skeleton className="mt-8 h-40 w-full" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10 text-center">
        <p className="text-muted-foreground">Research job not found.</p>
        <Button asChild className="mt-4">
          <Link to="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link to="/dashboard" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to dashboard
      </Link>

      <h1 className="text-xl font-semibold leading-snug tracking-tight">{job.query}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Mode: <span className="font-medium text-foreground">{job.mode}</span> · Started{" "}
        {new Date(job.created_at).toLocaleString()}
      </p>

      {job.status === "failed" ? (
        <FailedState error={job.error} />
      ) : (
        <Card className="mt-6">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-base">
              <span>{job.status === "completed" ? "Research completed" : "Researching..."}</span>
              <span className="text-sm font-normal text-muted-foreground">
                {statusProgressPercent(job.status)}%
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Progress value={statusProgressPercent(job.status)} />
            <p className="mt-3 text-sm text-muted-foreground">{STATUS_LABEL[job.status]}</p>

            {timeline.length > 0 && (
              <div className="mt-5 flex flex-col gap-1.5 border-t border-border pt-4">
                {timeline
                  .slice()
                  .reverse()
                  .slice(0, 12)
                  .map((event, i) => (
                    <p key={i} className="text-xs text-muted-foreground">
                      {describeEvent(event)}
                    </p>
                  ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {job.status === "completed" && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Results {results ? `(${results.length})` : ""}
          </h2>
          {results === undefined && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}
          {results && results.length === 0 && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                No results were found for this query. Try rephrasing it or switching to a deeper research mode.
              </CardContent>
            </Card>
          )}
          {results && results.length > 0 && (
            <div className="flex flex-col gap-3">
              {results.map((result) => (
                <ResultCard key={result.id} result={result} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultCard({ result }: { result: ResearchResult }) {
  const [showWhy, setShowWhy] = useState(false);
  const confidencePct = Math.round(result.confidence * 100);

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate font-medium">{result.title || result.url}</p>
            <a
              href={result.url}
              target="_blank"
              rel="noreferrer"
              className="mt-0.5 inline-flex items-center gap-1 truncate text-xs text-primary hover:underline"
            >
              {result.url}
              <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          </div>
          <Badge variant={confidencePct >= 70 ? "success" : confidencePct >= 40 ? "warning" : "outline"}>
            {confidencePct}%
          </Badge>
        </div>

        {result.snippet && <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">{result.snippet}</p>}

        <button
          type="button"
          onClick={() => setShowWhy((v) => !v)}
          className="mt-3 text-xs font-medium text-primary hover:underline"
        >
          {showWhy ? "Hide details" : "Why this score?"}
        </button>

        {showWhy && (
          <div className="mt-3 rounded-md bg-secondary/60 p-3 text-xs text-muted-foreground">
            <p className="mb-1 font-medium text-foreground">Basic relevance score — not a verified claim</p>
            <p>
              This score reflects whether the page was reachable and returned enough extractable content — it is
              not yet cross-checked against other sources. Multi-source verification, contradiction detection,
              and a full confidence breakdown (authority, freshness, evidence, consistency) land in a later
              phase — see the project&apos;s phase plan.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FailedState({ error }: { error: string | null }) {
  return (
    <Card className="mt-6 border-destructive/30">
      <CardContent className="flex gap-3 py-5">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
        <div>
          <p className="font-medium text-destructive">This research couldn&apos;t be completed</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error || "An unexpected error interrupted the research pipeline."}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            What you can do: start a new research with a refined query, or try a deeper mode which crawls more
            sources.
          </p>
          <Button asChild size="sm" className="mt-3">
            <Link to="/research/new">Start a new research</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
