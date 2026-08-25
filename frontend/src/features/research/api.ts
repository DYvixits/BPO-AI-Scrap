import { apiRequest } from "@/services/api";
import type { ResearchJob, ResearchJobDetail, ResearchMode, ResearchResult } from "@/types/api";

export interface CreateResearchInput {
  query: string;
  mode: ResearchMode;
  config?: Record<string, unknown>;
}

export function createResearch(input: CreateResearchInput) {
  return apiRequest<ResearchJob>("/research", { method: "POST", body: input });
}

export function listResearch() {
  return apiRequest<ResearchJob[]>("/research");
}

export function getResearch(id: string) {
  return apiRequest<ResearchJobDetail>(`/research/${id}`);
}

export function getResearchResults(id: string) {
  return apiRequest<ResearchResult[]>(`/research/${id}/results`);
}
