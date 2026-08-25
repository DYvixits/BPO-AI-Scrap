import type { ResearchEvent, ResearchStatus } from "@/types/api";

const STATUS_ORDER: ResearchStatus[] = [
  "created",
  "queued",
  "searching",
  "crawling",
  "extracting",
  "completed",
];

export function statusProgressPercent(status: ResearchStatus): number {
  if (status === "failed") return 100;
  const index = STATUS_ORDER.indexOf(status);
  if (index === -1) return 0;
  return Math.round((index / (STATUS_ORDER.length - 1)) * 100);
}

export const STATUS_LABEL: Record<ResearchStatus, string> = {
  created: "Preparing research plan",
  queued: "Queued — waiting for a worker",
  searching: "Searching for sources",
  crawling: "Crawling discovered pages",
  extracting: "Extracting and normalizing content",
  completed: "Research completed",
  failed: "Research failed",
};

export function describeEvent(event: ResearchEvent): string {
  const payload = event.payload as Record<string, unknown>;
  switch (event.kind) {
    case "status.changed":
      return `Status changed to "${payload.status}"`;
    case "search.completed":
      return `Found ${payload.count} candidate source${payload.count === 1 ? "" : "s"}`;
    case "sources.discovered":
      return `Registered ${payload.count} source${payload.count === 1 ? "" : "s"} to crawl`;
    case "page.completed": {
      if (!payload.duplicate) return `Crawled: ${payload.title || payload.url}`;
      const reason = payload.duplicate_reason === "near_duplicate" ? "near-duplicate" : "duplicate";
      return `Crawled: ${payload.title || payload.url} (${reason}, skipped)`;
    }
    case "page.failed":
      return `Could not access ${payload.url} — ${payload.error}`;
    case "crawl.expanded":
      return `Found ${payload.new_candidates} more page${payload.new_candidates === 1 ? "" : "s"} to consider from ${payload.from}`;
    case "crawl.stopped_early": {
      const reason =
        payload.reason === "objective_satisfied"
          ? "found what it was looking for"
          : "stopped finding anything new";
      return `Crawl stopped early after ${payload.pages_crawled} page${payload.pages_crawled === 1 ? "" : "s"} — ${reason}`;
    }
    case "entities.resolved":
      return `Grouped results into ${payload.count} compan${payload.count === 1 ? "y" : "ies"}`;
    case "research.completed":
      return `Done — ${payload.result_count} result${payload.result_count === 1 ? "" : "s"} found`;
    case "research.failed":
      return `Research failed — ${payload.error}`;
    default:
      return event.kind;
  }
}
