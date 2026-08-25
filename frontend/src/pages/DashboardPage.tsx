import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus, Search } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listResearch } from "@/features/research/api";
import type { ResearchStatus } from "@/types/api";

const STATUS_VARIANT: Record<ResearchStatus, "default" | "secondary" | "success" | "destructive"> = {
  created: "secondary",
  queued: "secondary",
  searching: "default",
  crawling: "default",
  extracting: "default",
  completed: "success",
  failed: "destructive",
};

export function DashboardPage() {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["research", "list"],
    queryFn: listResearch,
    refetchInterval: 5000,
  });

  const active = jobs?.filter((j) => !["completed", "failed"].includes(j.status)) ?? [];
  const completed = jobs?.filter((j) => j.status === "completed") ?? [];

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">An overview of your research activity.</p>
        </div>
        <Button asChild>
          <Link to="/research/new">
            <Plus className="h-4 w-4" />
            New Research
          </Link>
        </Button>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Active Research" value={isLoading ? undefined : active.length} />
        <StatCard label="Completed" value={isLoading ? undefined : completed.length} />
        <StatCard label="Total Research" value={isLoading ? undefined : jobs?.length ?? 0} />
        <StatCard
          label="Avg. Confidence"
          value={isLoading ? undefined : "—"}
          hint="Available once results include multi-source verification (Phase 6)"
        />
      </div>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Recent Research
      </h2>

      {isLoading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      {!isLoading && (!jobs || jobs.length === 0) && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
              <Search className="h-5 w-5 text-accent-foreground" />
            </div>
            <div>
              <p className="font-medium">No research yet.</p>
              <p className="text-sm text-muted-foreground">
                Start your first research to see results, sources, and evidence appear here.
              </p>
            </div>
            <Button asChild className="mt-2">
              <Link to="/research/new">Start your first research →</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && jobs && jobs.length > 0 && (
        <div className="flex flex-col gap-2">
          {jobs.map((job) => (
            <Link key={job.id} to={`/research/${job.id}`}>
              <Card className="transition-colors hover:border-primary/40">
                <CardContent className="flex items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{job.query}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()} · {job.mode}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <Badge variant={STATUS_VARIANT[job.status]}>{job.status}</Badge>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: number | string | undefined; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        {value === undefined ? (
          <Skeleton className="h-7 w-12" />
        ) : (
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        )}
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}
