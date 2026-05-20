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
export type InsightCategory = "functional" | "non_functional";
export type InsightCertainty = "explicit" | "implied";

export type Insight = {
  id: string;
  session_id: string;
  category: InsightCategory;
  certainty: InsightCertainty;
  text: string;
  original_text: string;
  source_quote: string;
  language: string;
  status: InsightStatus;
  created_at_iso: string;
};

export type AiStatus = "ok" | "no_model" | "offline" | "unknown";

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
  | { type: "ai_status"; state: Exclude<AiStatus, "unknown">; model: string; error?: string };
