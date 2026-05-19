import { useEffect, useState } from "react";
import { exportSession, startSession, stopSession } from "../lib/api";
import type { DeliveryStatus, RecordingState, Segment } from "../lib/types";
import GlassCard from "./GlassCard";

type Props = {
  state: RecordingState;
  sessionStart: number | null;
  segments: Segment[];
  deliveries: Map<string, DeliveryStatus>;
};

function fmtElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function Header({ state, sessionStart, segments, deliveries }: Props) {
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (state !== "recording") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [state]);

  const elapsedMs = sessionStart ? now - sessionStart : 0;
  const deliveredCount = Array.from(deliveries.values()).filter(
    (d) => d.status === "delivered",
  ).length;

  const dotClass = {
    idle: "bg-white/20",
    recording: "bg-red-500 animate-pulse",
    stopping: "bg-neon-amber animate-pulse",
    disconnected: "bg-neon-pink",
  }[state];

  const dotLabel = {
    idle: "Idle",
    recording: "Recording",
    stopping: "Stopping…",
    disconnected: "Backend offline",
  }[state];

  const handle = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onExport = async () => {
    const data = await exportSession();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session-${data.session_id ?? "unknown"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <GlassCard className="px-6 py-4 flex items-center gap-6">
      <div className="flex items-center gap-3">
        <span className={`inline-block w-3 h-3 rounded-full ${dotClass}`} />
        <span className="text-sm font-medium">{dotLabel}</span>
      </div>
      <div className="font-mono text-2xl text-white/90 tabular-nums">
        {fmtElapsed(elapsedMs)}
      </div>
      <div className="flex gap-5 text-sm text-white/60">
        <span>
          Segments <span className="text-white">{segments.length}</span>
        </span>
        <span>
          Delivered{" "}
          <span className="text-white">
            {deliveredCount}/{segments.length}
          </span>
        </span>
      </div>
      <div className="ml-auto flex gap-2">
        {state === "idle" || state === "disconnected" ? (
          <button
            onClick={() => handle(startSession)}
            disabled={busy || state === "disconnected"}
            className="px-4 py-2 rounded-lg bg-neon-blue hover:bg-neon-blue/80 disabled:opacity-40 text-sm font-medium"
          >
            ▶ Start
          </button>
        ) : (
          <button
            onClick={() => handle(stopSession)}
            disabled={busy || state === "stopping"}
            className="px-4 py-2 rounded-lg bg-neon-pink hover:bg-neon-pink/80 disabled:opacity-40 text-sm font-medium"
          >
            ■ Stop
          </button>
        )}
        <button
          onClick={onExport}
          className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm font-medium"
        >
          ↓ Export
        </button>
      </div>
    </GlassCard>
  );
}
