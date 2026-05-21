import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Clock, BookText, Cpu, Download, Sparkles, Cloud, KeyRound } from "lucide-react";
import { NavHeader, NavTab } from "./ui/nav-header";
import {
  getApiKeyStatus,
  getModel,
  getVocabulary,
  listHistory,
  setApiKey as setApiKeyApi,
  setModel as setModelApi,
  setVocabulary as setVocabularyApi,
} from "../lib/api";
import type { ApiKeyStatus } from "../lib/api";
import type { PastSessionSummary } from "../lib/types";
import { cn } from "../lib/utils";

type Props = {
  onSelectPast: (id: string) => void;
};

type ModelKind = "local" | "cloud";
type ModelEntry = {
  id: string;
  label: string;
  hint: string;
  kind: ModelKind;
  provider?: "openai" | "anthropic";
};

const MODELS: readonly ModelEntry[] = [
  { id: "phi3", label: "phi3", hint: "fast (~2.4 GB)", kind: "local" },
  { id: "phi4-mini:3.8b", label: "phi4-mini", hint: "newer phi (~2.5 GB)", kind: "local" },
  { id: "mistral", label: "mistral", hint: "stronger German (~4 GB)", kind: "local" },
  { id: "llama3.1", label: "llama3.1", hint: "best reasoning (~5 GB)", kind: "local" },
  { id: "qwen3:8b", label: "qwen3 8B", hint: "newest qwen, very capable (~5.2 GB)", kind: "local" },
  { id: "openai/gpt-4o-mini", label: "gpt-4o-mini", hint: "OpenAI · fast & cheap", kind: "cloud", provider: "openai" },
  { id: "anthropic/claude-haiku-4-5", label: "claude-haiku-4-5", hint: "Anthropic · fast", kind: "cloud", provider: "anthropic" },
] as const;

function shortModelLabel(id: string): string {
  const m = MODELS.find((m) => m.id === id);
  return m ? m.label : id;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  if (m === 0) return `${rem}s`;
  return `${m}m ${rem}s`;
}

export default function AppNav({ onSelectPast }: Props) {
  const [open, setOpen] = useState<null | "history" | "vocab" | "model">(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // History
  const [history, setHistory] = useState<PastSessionSummary[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Vocabulary
  const [vocab, setVocab] = useState("");
  const [vocabDraft, setVocabDraft] = useState("");
  const [vocabSaving, setVocabSaving] = useState(false);

  // Model
  const [model, setModelState] = useState<string>("phi3");
  const [modelSaving, setModelSaving] = useState(false);

  // API keys
  const [keyStatus, setKeyStatus] = useState<ApiKeyStatus>({ openai: false, anthropic: false });
  const [openaiDraft, setOpenaiDraft] = useState("");
  const [anthropicDraft, setAnthropicDraft] = useState("");
  const [keysSaving, setKeysSaving] = useState<"openai" | "anthropic" | null>(null);

  useEffect(() => {
    getVocabulary().then((t) => {
      setVocab(t);
      setVocabDraft(t);
    }).catch(() => {});
    getModel().then((m) => setModelState(m.model)).catch(() => {});
    getApiKeyStatus().then(setKeyStatus).catch(() => {});
  }, []);

  const handleKeySave = async (provider: "openai" | "anthropic") => {
    if (keysSaving) return;
    const draft = provider === "openai" ? openaiDraft : anthropicDraft;
    setKeysSaving(provider);
    try {
      const next = await setApiKeyApi(provider, draft);
      setKeyStatus(next);
      if (provider === "openai") setOpenaiDraft("");
      else setAnthropicDraft("");
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setKeysSaving(null);
    }
  };

  const handleKeyClear = async (provider: "openai" | "anthropic") => {
    if (keysSaving) return;
    setKeysSaving(provider);
    try {
      const next = await setApiKeyApi(provider, "");
      setKeyStatus(next);
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setKeysSaving(null);
    }
  };

  useEffect(() => {
    if (open !== "history") return;
    setHistoryLoading(true);
    listHistory()
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [open]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(null);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  const handleVocabSave = async () => {
    setVocabSaving(true);
    try {
      const saved = await setVocabularyApi(vocabDraft);
      setVocab(saved);
      setOpen(null);
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setVocabSaving(false);
    }
  };

  const handleModelPick = async (id: string) => {
    if (id === model || modelSaving) return;
    setModelSaving(true);
    try {
      const next = await setModelApi(id);
      setModelState(next);
      setOpen(null);
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setModelSaving(false);
    }
  };

  return (
    <nav className="sticky top-0 z-40 bg-transparent">
      <div ref={wrapRef} className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between gap-6">
        {/* Left: brand */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-neon-cyan to-neon-blue flex items-center justify-center shadow-[0_0_12px_rgba(1,181,226,0.4)]">
            <Sparkles className="w-4 h-4 text-black" />
          </div>
          <span className="text-sm font-semibold text-white tracking-tight">doings</span>
          <span className="text-[10px] text-white/30 uppercase tracking-wider ml-1">
            local
          </span>
        </div>

        {/* Right: pill nav with hover-cursor */}
        <NavHeader>
          <NavTab
            active={open === "history"}
            onClick={() => setOpen(open === "history" ? null : "history")}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>History</span>
          </NavTab>

          <NavTab
            active={open === "vocab"}
            onClick={() => {
              setVocabDraft(vocab);
              setOpen(open === "vocab" ? null : "vocab");
            }}
          >
            <BookText className="w-3.5 h-3.5" />
            <span>Vocabulary</span>
            {vocab && (
              <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] tracking-wider bg-white/20">
                {vocab.split(/[,;\s]+/).filter(Boolean).length}
              </span>
            )}
          </NavTab>

          <NavTab
            active={open === "model"}
            onClick={() => setOpen(open === "model" ? null : "model")}
          >
            {MODELS.find((m) => m.id === model)?.kind === "cloud" ? (
              <Cloud className="w-3.5 h-3.5" />
            ) : (
              <Cpu className="w-3.5 h-3.5" />
            )}
            <span>{shortModelLabel(model)}</span>
          </NavTab>

          <NavTab disabled title="Available in Step 4">
            <Download className="w-3.5 h-3.5" />
            <span>Export</span>
            <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] tracking-wider bg-white/10 text-white/40">
              soon
            </span>
          </NavTab>
        </NavHeader>

        {/* Dropdown panels */}
        <AnimatePresence>
          {open === "history" && (
            <Panel align="right-44">
              <div className="text-[10px] uppercase tracking-wider text-white/40 px-4 pt-3 pb-2">
                Past Sessions
              </div>
              {historyLoading && (
                <div className="px-4 py-3 text-xs text-white/40">Loading…</div>
              )}
              {!historyLoading && history?.length === 0 && (
                <div className="px-4 py-4 text-xs text-white/40 leading-snug">
                  No past sessions yet. Stop and start a new one to populate.
                </div>
              )}
              {!historyLoading &&
                history?.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => {
                      onSelectPast(s.session_id);
                      setOpen(null);
                    }}
                    className="w-full px-4 py-2.5 text-left hover:bg-white/5 border-t border-white/5 first:border-0"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-white/80 font-mono truncate">
                        {fmtTime(s.ended_at_iso)}
                      </span>
                      <span className="text-[10px] text-white/40 uppercase tracking-wider">
                        {s.languages.join(" / ").toUpperCase() || "—"}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[10px] text-white/40">
                      {s.segment_count} segments · {fmtDuration(s.duration_s)}
                    </div>
                  </button>
                ))}
            </Panel>
          )}

          {open === "vocab" && (
            <Panel align="right-32">
              <div className="px-4 pt-3">
                <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">
                  Meeting Vocabulary
                </div>
                <p className="text-[11px] text-white/40 leading-snug mb-2">
                  Domain jargon, names, acronyms. Whisper uses this as a hint to spell
                  uncommon words correctly. Applies on the next ▶ Start.
                </p>
                <textarea
                  value={vocabDraft}
                  onChange={(e) => setVocabDraft(e.target.value)}
                  rows={4}
                  placeholder="e.g. Salesforce, B2B SaaS, Telekom, KPI, Q4 OKRs"
                  className="w-full text-xs bg-black/40 border border-white/10 rounded-md px-2.5 py-2 text-white placeholder:text-white/25 focus:outline-none focus:border-neon-cyan/60 resize-none font-mono"
                />
              </div>
              <div className="px-4 pb-3 pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setOpen(null)}
                  className="px-3 py-1 rounded-md text-[11px] text-white/60 hover:text-white hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  onClick={handleVocabSave}
                  disabled={vocabSaving || vocabDraft === vocab}
                  className="px-3 py-1 rounded-md text-[11px] font-medium text-neon-cyan bg-neon-cyan/10 border border-neon-cyan/40 hover:bg-neon-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {vocabSaving ? "Saving…" : "Save"}
                </button>
              </div>
            </Panel>
          )}

          {open === "model" && (
            <Panel align="right-12" wide>
              <div className="text-[10px] uppercase tracking-wider text-white/40 px-4 pt-3 pb-1">
                Local Model · Ollama
              </div>
              {MODELS.filter((m) => m.kind === "local").map((m) => (
                <ModelRow
                  key={m.id}
                  entry={m}
                  active={model === m.id}
                  disabled={modelSaving}
                  onPick={() => handleModelPick(m.id)}
                />
              ))}

              <div className="text-[10px] uppercase tracking-wider text-white/40 px-4 pt-4 pb-1 border-t border-white/5 mt-1">
                Cloud Model
              </div>
              {MODELS.filter((m) => m.kind === "cloud").map((m) => {
                const keySet = m.provider ? keyStatus[m.provider] : false;
                return (
                  <ModelRow
                    key={m.id}
                    entry={m}
                    active={model === m.id}
                    disabled={modelSaving || !keySet}
                    onPick={() => handleModelPick(m.id)}
                    hintSuffix={keySet ? undefined : "API key required"}
                  />
                );
              })}

              <div className="text-[10px] uppercase tracking-wider text-white/40 px-4 pt-4 pb-1 border-t border-white/5 mt-1 flex items-center gap-1.5">
                <KeyRound className="w-3 h-3" /> API Keys
              </div>
              <p className="text-[11px] text-white/40 leading-snug px-4 pb-2">
                Held in memory only. Env vars OPENAI_API_KEY / ANTHROPIC_API_KEY set on startup are loaded automatically.
              </p>
              <KeyRow
                label="OpenAI"
                placeholder="sk-…"
                draft={openaiDraft}
                onDraft={setOpenaiDraft}
                isSet={keyStatus.openai}
                saving={keysSaving === "openai"}
                onSave={() => handleKeySave("openai")}
                onClear={() => handleKeyClear("openai")}
              />
              <KeyRow
                label="Anthropic"
                placeholder="sk-ant-…"
                draft={anthropicDraft}
                onDraft={setAnthropicDraft}
                isSet={keyStatus.anthropic}
                saving={keysSaving === "anthropic"}
                onSave={() => handleKeySave("anthropic")}
                onClear={() => handleKeyClear("anthropic")}
              />
            </Panel>
          )}
        </AnimatePresence>
      </div>
    </nav>
  );
}

function Panel({
  align,
  children,
  wide,
}: {
  align: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15 }}
      className={cn(
        "absolute top-full mt-1 rounded-xl border border-white/10 bg-black/85 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden",
        wide ? "w-[22rem] max-h-[80vh] overflow-y-auto" : "w-80",
        align,
      )}
    >
      {children}
    </motion.div>
  );
}

function ModelRow({
  entry,
  active,
  disabled,
  onPick,
  hintSuffix,
}: {
  entry: ModelEntry;
  active: boolean;
  disabled: boolean;
  onPick: () => void;
  hintSuffix?: string;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onPick}
      className={cn(
        "w-full px-4 py-2 text-left hover:bg-white/5 border-t border-white/5 first:border-0 flex items-center justify-between gap-3",
        disabled && "opacity-40 cursor-not-allowed",
      )}
    >
      <div className="min-w-0">
        <div className="text-xs text-white font-mono truncate">{entry.label}</div>
        <div className="text-[10px] text-white/40 truncate">
          {entry.hint}
          {hintSuffix && <span className="text-neon-amber"> · {hintSuffix}</span>}
        </div>
      </div>
      {active && (
        <span className="text-[10px] text-neon-cyan uppercase tracking-wider shrink-0">
          Active
        </span>
      )}
    </button>
  );
}

function KeyRow({
  label,
  placeholder,
  draft,
  onDraft,
  isSet,
  saving,
  onSave,
  onClear,
}: {
  label: string;
  placeholder: string;
  draft: string;
  onDraft: (v: string) => void;
  isSet: boolean;
  saving: boolean;
  onSave: () => void;
  onClear: () => void;
}) {
  return (
    <div className="px-4 py-2 border-t border-white/5 first:border-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-medium text-white/70">{label}</span>
        <span
          className={cn(
            "text-[10px] uppercase tracking-wider",
            isSet ? "text-neon-green" : "text-white/30",
          )}
        >
          {isSet ? "set" : "not set"}
        </span>
      </div>
      <div className="flex gap-1.5">
        <input
          type="password"
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder={placeholder}
          className="flex-1 min-w-0 text-[11px] bg-black/40 border border-white/10 rounded-md px-2 py-1 text-white placeholder:text-white/25 focus:outline-none focus:border-neon-cyan/60 font-mono"
        />
        <button
          onClick={onSave}
          disabled={saving || !draft.trim()}
          className="px-2.5 py-1 rounded-md text-[10px] font-medium text-neon-cyan bg-neon-cyan/10 border border-neon-cyan/40 hover:bg-neon-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? "…" : "Save"}
        </button>
        {isSet && (
          <button
            onClick={onClear}
            disabled={saving}
            className="px-2.5 py-1 rounded-md text-[10px] text-white/60 hover:text-white hover:bg-white/5 disabled:opacity-40"
            title="Clear in-memory key"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
