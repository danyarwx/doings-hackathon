export type Segment = {
  id: string;
  session_id: string;
  text: string;
  start_s: number;
  end_s: number;
  lang: string;
};

export type InsightType = "requirement" | "action_item" | "decision" | "chatter";

export type InsightStatus = "pending" | "approved" | "rejected";

export type Insight = {
  id: string;
  segment_id: string;
  type: InsightType;
  text: string;
  source_quote: string;
  language: string;
  confidence: number;
  needs_review: boolean;
  status: InsightStatus;
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
  | { type: "delivery"; id: string; status: string; attempts: number };
