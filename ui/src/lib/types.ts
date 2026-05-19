export type Segment = {
  id: string;
  session_id: string;
  text: string;
  start_s: number;
  end_s: number;
  lang: string;
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
