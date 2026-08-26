export type Role =
  | "super_admin"
  | "admin"
  | "research_manager"
  | "researcher"
  | "analyst"
  | "viewer"
  | "api_client";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  organization: Organization;
  role: Role;
}

export type ResearchMode = "quick" | "balanced" | "deep" | "verified" | "investigation" | "custom";

export type ResearchStatus =
  | "created"
  | "queued"
  | "searching"
  | "crawling"
  | "extracting"
  | "completed"
  | "failed";

export interface ResearchObjective {
  target_entities: string[];
  geography: string[];
  industry: string[];
  company_size_min: number | null;
  company_size_max: number | null;
  required_attributes: string[];
  signals: string[];
  freshness: string;
  matched_keywords: Record<string, string[]>;
}

export interface ResearchJob {
  id: string;
  query: string;
  status: ResearchStatus;
  mode: ResearchMode;
  config: Record<string, unknown>;
  objective: ResearchObjective;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ResearchEvent {
  kind: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ResearchJobDetail extends ResearchJob {
  events: ResearchEvent[];
}

export interface ResearchResult {
  id: string;
  title: string | null;
  url: string;
  snippet: string | null;
  confidence: number;
  company_id: string | null;
}

export interface EntityAlias {
  alias_type: "name" | "domain";
  value: string;
  source_url: string;
}

export type TruthStatus = "unverifiable" | "uncertain" | "corroborated" | "verified" | "outdated";

export interface Evidence {
  source_url: string;
  domain: string;
  excerpt: string | null;
}

export interface ConfidenceScore {
  status: TruthStatus;
  source_count: number;
  source_diversity: number;
  freshness_score: number;
  evidence_completeness: number;
  overall_score: number;
}

export type CommercialSignalType =
  | "hiring"
  | "expansion"
  | "funding"
  | "acquisition"
  | "leadership_change"
  | "product_launch"
  | "digital_transformation"
  | "layoffs"
  | "closure";

export interface CommercialSignal {
  signal_type: CommercialSignalType;
  polarity: "positive" | "negative";
  matched_keyword: string;
  excerpt: string;
  source_url: string;
  base_weight: number;
  decayed_strength: number;
}

export interface Company {
  id: string;
  canonical_name: string;
  primary_domain: string;
  description: string | null;
  match_confidence: number;
  aliases: EntityAlias[];
  confidence_score: ConfidenceScore | null;
  evidence: Evidence[];
  signals: CommercialSignal[];
}
