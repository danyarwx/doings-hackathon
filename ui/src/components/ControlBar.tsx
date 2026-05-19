import { useState } from "react";
import { pauseSession, startSession, stopSession } from "../lib/api";
import type { RecordingState } from "../lib/types";
import { VoicePoweredOrb } from "./ui/voice-powered-orb";

type Props = { state: RecordingState };

export default function ControlBar({ state }: Props) {
  const [busy, setBusy] = useState(false);

  const recording = state === "recording";
  const paused = state === "paused";
  const idle = state === "idle";
  const stopping = state === "stopping";
  const disconnected = state === "disconnected";

  const canStartOrResume = idle || paused;
  const leftLabel = recording ? "Pause recording" : disconnected ? "Backend offline" : "Start recording";
  const leftGlyph = recording ? "⏸" : "▶";
  const leftAction = recording ? pauseSession : startSession;
  const leftDisabled = busy || stopping || disconnected || (!canStartOrResume && !recording);

  const stopDisabled = busy || idle || disconnected || stopping;

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
    <div className="flex items-center justify-center gap-6 py-2">
      <button
        onClick={() => handle(leftAction)}
        disabled={leftDisabled}
        title={leftLabel}
        className="w-14 h-14 rounded-full grid place-items-center bg-white/5 border border-white/10 hover:bg-neon-blue/30 hover:border-neon-blue/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <span className={"text-2xl text-white " + (recording ? "" : "translate-x-[2px]")}>
          {leftGlyph}
        </span>
      </button>

      <div className="w-32 h-32">
        <VoicePoweredOrb enableVoiceControl={recording} />
      </div>

      <button
        onClick={() => handle(stopSession)}
        disabled={stopDisabled}
        title="Stop recording"
        className="w-14 h-14 rounded-full grid place-items-center bg-white/5 border border-white/10 hover:bg-neon-pink/30 hover:border-neon-pink/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <span className="text-2xl text-white">■</span>
      </button>
    </div>
  );
}
