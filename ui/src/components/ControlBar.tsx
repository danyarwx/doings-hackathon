import { useState } from "react";
import { startSession, stopSession } from "../lib/api";
import type { RecordingState } from "../lib/types";

const WAVE_BARS = 14;

type Props = { state: RecordingState };

export default function ControlBar({ state }: Props) {
  const [busy, setBusy] = useState(false);
  const recording = state === "recording";
  const stopping = state === "stopping";
  const disconnected = state === "disconnected";

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

  return (
    <div className="flex items-center justify-center gap-6 py-4">
      <button
        onClick={() => handle(startSession)}
        disabled={busy || recording || stopping || disconnected}
        title={disconnected ? "Backend offline" : "Start recording"}
        className="w-14 h-14 rounded-full grid place-items-center bg-white/5 border border-white/10 hover:bg-neon-blue/30 hover:border-neon-blue/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <span className="text-2xl text-white translate-x-[2px]">▶</span>
      </button>

      <Wave active={recording} />

      <button
        onClick={() => handle(stopSession)}
        disabled={busy || !recording}
        title="Stop recording"
        className="w-14 h-14 rounded-full grid place-items-center bg-white/5 border border-white/10 hover:bg-neon-pink/30 hover:border-neon-pink/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <span className="text-2xl text-white">■</span>
      </button>
    </div>
  );
}

function Wave({ active }: { active: boolean }) {
  return (
    <div className="flex items-center gap-1 h-12 px-2">
      {Array.from({ length: WAVE_BARS }).map((_, i) => (
        <span
          key={i}
          className={
            "w-1 rounded-full " +
            (active
              ? "bg-neon-cyan animate-wave"
              : "bg-white/20")
          }
          style={{
            height: active ? undefined : "20%",
            animationDelay: `${(i * 80) % 600}ms`,
          }}
        />
      ))}
    </div>
  );
}
