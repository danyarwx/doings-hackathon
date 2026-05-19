import { useEffect, useRef, useState } from "react";
import type { RecordingState, Segment, WsMessage } from "./types";

export type SessionView = {
  state: RecordingState;
  sessionId: string | null;
  segments: Segment[];
};

const RECONNECT_BACKOFF_MS = [1000, 2000, 4000, 8000, 10000];

export function useSessionWs(): SessionView {
  const [state, setState] = useState<RecordingState>("disconnected");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
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
            // New session id from backend → clear stale segments from the
            // previous run. Same id (e.g. resume after pause) keeps them.
            if (msg.session_id && msg.session_id !== prevId) {
              setSegments([]);
            }
            return msg.session_id;
          });
        } else if (msg.type === "segment") {
          setSegments((prev) => [...prev, msg.segment]);
        }
        // "delivery" messages are still sent by the backend; ignored in this UI.
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

  return { state, sessionId, segments };
}
