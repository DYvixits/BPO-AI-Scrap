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
import { getResearch, getResearchCompanies, getResearchResults } from "@/features/research/api";
import { useResearchEvents } from "@/features/research/useResearchEvents";
import type { Company, ResearchEvent, ResearchObjective, ResearchResult } from "@/types/api";

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

  const { data: companies } = useQuery({
    queryKey: ["research", id, "companies"],
    queryFn: () => getResearchCompanies(id as string),
    enabled: !!id && job?.status === "completed",
  });

  const groupedResults = useMemo(() => {
    if (!results) return [];
    const companyById = new Map((companies ?? []).map((c) => [c.id, c]));
    const groups = new Map<string, { company: Company | null; results: ResearchResult[] }>();
    for (const result of results) {
      const key = result.company_id ?? "__ungrouped__";
      if (!groups.has(key)) {
        groups.set(key, { company: result.company_id ? (companyById.get(result.company_id) ?? null) : null, results: [] });
      }
      groups.get(key)!.results.push(result);
    }
    // Grouped companies first (most members first — the most consolidated
    // picture of a company), ungrouped results last.
    return [...groups.values()].sort((a, b) => {
      if (!a.company) return 1;
      if (!b.company) return -1;
      return b.results.length - a.results.length;
    });
  }, [results, companies]);

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

      <ObjectiveChips objective={job.objective} />

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
            <div className="flex flex-col gap-4">
              {groupedResults.map((group, i) => (
                <CompanyGroup key={group.company?.id ?? `ungrouped-${i}`} group={group} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ObjectiveChips({ objective }: { objective: ResearchObjective }) {
  const chips: { label: string; value: string }[] = [];
  if (objective.industry.length) chips.push({ label: "Industry", value: objective.industry.join(", ") });
  if (objective.geography.length) chips.push({ label: "Geography", value: objective.geography.join(", ") });
  if (objective.company_size_min || objective.company_size_max) {
    const min = objective.company_size_min;
    const max = objective.company_size_max;
    chips.push({
      label: "Company size",
      value: min && max ? `${min}-${max} employees` : min ? `${min}+ employees` : `<${max} employees`,
    });
  }
  if (objective.signals.length) {
    chips.push({ label: "Signals", value: objective.signals.map((s) => s.replace(/_/g, " ")).join(", ") });
  }
  if (objective.freshness === "recent") chips.push({ label: "Freshness", value: "recent" });
  if (objective.target_entities.includes("person")) chips.push({ label: "Also finding", value: "people/contacts" });

  if (chips.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-muted-foreground">Understood as:</span>
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/60 px-2.5 py-0.5 text-xs"
          title={`Matched from your query — see the API response's objective.matched_keywords for the exact words.`}
        >
          <span className="text-muted-foreground">{chip.label}:</span>
          <span className="font-medium text-foreground">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

function CompanyGroup({
  group,
}: {
  group: { company: Company | null; results: ResearchResult[] };
}) {
  const { company, results } = group;

  if (!company) {
    return (
      <div className="flex flex-col gap-3">
        {results.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Not grouped into a company (no site name found to resolve by)
          </p>
        )}
        {results.map((result) => (
          <ResultCard key={result.id} result={result} />
        ))}
      </div>
    );
  }

  const confidencePct = Math.round(company.match_confidence * 100);
  const domainAliases = company.aliases.filter((a) => a.alias_type === "domain");

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1 border-b border-border pb-1.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 className="font-medium">{company.canonical_name}</h3>
          {domainAliases.length > 1 && (
            <span
              className="rounded-full bg-secondary/60 px-2 py-0.5 text-xs text-muted-foreground"
              title={`Entity Resolution merged ${domainAliases.length} sources into this company — see aliases below.`}
            >
              {domainAliases.length} sources merged · {confidencePct}% match confidence
            </span>
          )}
        </div>
        {company.description && (
          <span className="truncate text-xs text-muted-foreground">{company.description}</span>
        )}
      </div>
      <div className="flex flex-col gap-3">
        {results.map((result) => (
          <ResultCard key={result.id} result={result} />
        ))}
      </div>
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
