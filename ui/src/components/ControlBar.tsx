import { useState } from "react";
import { pauseSession, startSession, stopSession } from "../lib/api";
import type { RecordingState } from "../lib/types";
import { LanguageSwitcher, type Lang } from "./ui/language-switcher";
import { VoicePoweredOrb } from "./ui/voice-powered-orb";

type Props = { state: RecordingState };

const LANG_STORAGE_KEY = "doings.language";

function loadLang(): Lang {
  const v = localStorage.getItem(LANG_STORAGE_KEY);
  if (v === "de" || v === "en" || v === "auto") return v;
  return "auto";
}

export default function ControlBar({ state }: Props) {
  const [busy, setBusy] = useState(false);
  const [language, setLanguage] = useState<Lang>(loadLang());

  const recording = state === "recording";
  const paused = state === "paused";
  const idle = state === "idle";
  const stopping = state === "stopping";
  const disconnected = state === "disconnected";

  const canStartOrResume = idle || paused;
  const leftLabel = recording
    ? "Pause recording"
    : disconnected
      ? "Backend offline"
      : "Start recording";
  const leftGlyph = recording ? "⏸" : "▶";
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

  const handleLangChange = (v: Lang) => {
    setLanguage(v);
    localStorage.setItem(LANG_STORAGE_KEY, v);
  };

  const handleLeft = () => {
    if (recording) return handle(pauseSession);
    return handle(() => startSession({ language: language === "auto" ? null : language }));
  };

  return (
    <div className="flex flex-col items-center gap-3 py-2">
      <LanguageSwitcher
        value={language}
        onValueChange={handleLangChange}
        disabled={recording || paused || stopping}
      />
      <div className="flex items-center justify-center gap-6">
        <button
          onClick={handleLeft}
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
    </div>
  );
}
