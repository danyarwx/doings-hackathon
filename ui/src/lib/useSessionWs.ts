import { useEffect, useRef, useState } from "react";
import type {
  AiStatus,
  ExportDraft,
  Insight,
  RecordingState,
  Segment,
  WsMessage,
} from "./types";

export type SessionView = {
  state: RecordingState;
  sessionId: string | null;
  segments: Segment[];
  insights: Insight[];
  aiStatus: AiStatus;
  exportDraft: ExportDraft | null;
  setExportDraft: (d: ExportDraft | null) => void;
};

const RECONNECT_BACKOFF_MS = [1000, 2000, 4000, 8000, 10000];

export function useSessionWs(): SessionView {
  const [state, setState] = useState<RecordingState>("disconnected");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [aiStatus, setAiStatus] = useState<AiStatus>("unknown");
  const [exportDraft, setExportDraft] = useState<ExportDraft | null>(null);
  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/ws`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
      };

      ws.onmessage = (ev) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type === "state") {
          setState(msg.state);
          setSessionId((prevId) => {
            if (msg.session_id && msg.session_id !== prevId) {
              setSegments([]);
              setInsights([]);
              setExportDraft(null);
            }
            return msg.session_id;
          });
        } else if (msg.type === "segment") {
          setSegments((prev) => [...prev, msg.segment]);
        } else if (msg.type === "insight") {
          setInsights((prev) => {
            // Late snapshots may re-send; replace by id if present.
            const idx = prev.findIndex((i) => i.id === msg.insight.id);
            if (idx >= 0) {
              const next = prev.slice();
              next[idx] = msg.insight;
              return next;
            }
            return [...prev, msg.insight];
          });
        } else if (msg.type === "insight_update") {
          setInsights((prev) =>
            prev.map((i) =>
              i.id === msg.id ? { ...i, status: msg.status, text: msg.text } : i,
            ),
          );
        } else if (msg.type === "ai_status") {
          setAiStatus(msg.state);
        } else if (msg.type === "export_draft") {
          setExportDraft(msg.draft);
        }
        // "delivery" messages ignored in this UI.
      };

      ws.onclose = () => {
        if (cancelled) return;
        setState("disconnected");
        const delay =
          RECONNECT_BACKOFF_MS[
            Math.min(attemptRef.current, RECONNECT_BACKOFF_MS.length - 1)
          ];
        attemptRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  return { state, sessionId, segments, insights, aiStatus, exportDraft, setExportDraft };
}
