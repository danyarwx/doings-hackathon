export type Segment = {
  id: string;
  session_id: string;
  text: string;
  start_s: number;
  end_s: number;
  lang: string;
};

export type PastSessionSummary = {
  session_id: string;
  ended_at_iso: string;
  segment_count: number;
  duration_s: number;
  languages: string[];
};

export type PastSession = {
  session_id: string;
  ended_at_iso: string;
  segments: Segment[];
};

export type InsightStatus = "pending" | "approved" | "declined";

export type Insight = {
  id: string;
  session_id: string;
  text: string;
  original_text: string;
  source_quote: string;
  detail: string;
  language: string;
  status: InsightStatus;
  created_at_iso: string;
};

export type AiStatus = "ok" | "no_model" | "offline" | "loading" | "thinking" | "unknown";

export type InvestValidation = {
  independent: boolean;
  negotiable: boolean;
  valuable: boolean;
  estimable: boolean;
  small: boolean;
  testable: boolean;
};

export type ExportRequirement = {
  issuetype: "Story" | "Task" | "Bug" | "Epic";
  summary: string;
  description: {
    user_story: { given: string; when: string; then: string };
    acceptance_criteria: string[];
    invest_validation: InvestValidation;
  };
  priority: "high" | "medium" | "low";
  labels: string[];
  story_points: number | null;
};

export type ExportDecision = { summary: string };

export type ExportDraft = {
  requirements: ExportRequirement[];
  decisions: ExportDecision[];
};

export type RecordingState =
  | "idle"
  | "recording"
  | "paused"
  | "stopping"
  | "disconnected";

export type WsMessage =
  | { type: "state"; state: Exclude<RecordingState, "disconnected">; session_id: string | null }
  | { type: "segment"; segment: Segment }
  | { type: "delivery"; id: string; status: string; attempts: number }
  | { type: "insight"; insight: Insight }
  | { type: "insight_update"; id: string; status: InsightStatus; text: string }
  | { type: "ai_status"; state: Exclude<AiStatus, "unknown">; model: string; error?: string }
  | { type: "export_draft"; draft: ExportDraft };
