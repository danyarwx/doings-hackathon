import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Clock, BookText, Cpu, Download, ChevronDown, Sparkles } from "lucide-react";
import {
  getModel,
  getVocabulary,
  listHistory,
  setModel as setModelApi,
  setVocabulary as setVocabularyApi,
} from "../lib/api";
import type { PastSessionSummary } from "../lib/types";
import { cn } from "../lib/utils";

type Props = {
  onSelectPast: (id: string) => void;
};

const MODELS = [
  { id: "phi3", label: "phi3", hint: "fast (~2.4 GB)" },
  { id: "phi4-mini:3.8b", label: "phi4-mini", hint: "newer phi, stronger (~2.5 GB)" },
  { id: "mistral", label: "mistral", hint: "stronger German (~4 GB)" },
  { id: "llama3.1", label: "llama3.1", hint: "best reasoning (~5 GB)" },
  { id: "qwen3:8b", label: "qwen3 8B", hint: "newest qwen, very capable (~5.2 GB)" },
] as const;

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

  useEffect(() => {
    getVocabulary().then((t) => {
      setVocab(t);
      setVocabDraft(t);
    }).catch(() => {});
    getModel().then((m) => setModelState(m.model)).catch(() => {});
  }, []);

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
    <nav className="sticky top-0 z-40 bg-black/40 backdrop-blur-xl border-b border-white/5">
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

        {/* Right: actions */}
        <div className="flex items-center gap-1">
          {/* History */}
          <NavButton
            active={open === "history"}
            onClick={() => setOpen(open === "history" ? null : "history")}
            icon={<Clock className="w-3.5 h-3.5" />}
            label="History"
          />

          {/* Vocabulary */}
          <NavButton
            active={open === "vocab"}
            onClick={() => {
              setVocabDraft(vocab);
              setOpen(open === "vocab" ? null : "vocab");
            }}
            icon={<BookText className="w-3.5 h-3.5" />}
            label="Vocabulary"
            badge={vocab ? `${vocab.split(/[,;\s]+/).filter(Boolean).length} words` : undefined}
          />

          {/* Model picker */}
          <NavButton
            active={open === "model"}
            onClick={() => setOpen(open === "model" ? null : "model")}
            icon={<Cpu className="w-3.5 h-3.5" />}
            label={model}
            withChevron
          />

          <div className="w-px h-5 bg-white/10 mx-2" />

          {/* Export (disabled) */}
          <button
            disabled
            title="Available in Step 4"
            className="text-xs py-1.5 px-3 flex items-center gap-1.5 uppercase tracking-wider font-medium text-white/25 cursor-not-allowed"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export</span>
            <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider bg-white/5 text-white/30">
              soon
            </span>
          </button>
        </div>

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
            <Panel align="right-12">
              <div className="text-[10px] uppercase tracking-wider text-white/40 px-4 pt-3 pb-1">
                Local Model
              </div>
              <p className="text-[11px] text-white/40 leading-snug px-4 pb-2">
                Active model for AI insights. Swap any time.
              </p>
              {MODELS.map((m) => (
                <button
                  key={m.id}
                  disabled={modelSaving}
                  onClick={() => handleModelPick(m.id)}
                  className={cn(
                    "w-full px-4 py-2.5 text-left hover:bg-white/5 border-t border-white/5 first:border-0 flex items-center justify-between gap-3",
                    modelSaving && "opacity-40",
                  )}
                >
                  <div>
                    <div className="text-xs text-white font-mono">{m.label}</div>
                    <div className="text-[10px] text-white/40">{m.hint}</div>
                  </div>
                  {model === m.id && (
                    <span className="text-[10px] text-neon-cyan uppercase tracking-wider">
                      Active
                    </span>
                  )}
                </button>
              ))}
            </Panel>
          )}
        </AnimatePresence>
      </div>
    </nav>
  );
}

function NavButton({
  active,
  onClick,
  icon,
  label,
  badge,
  withChevron,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: string;
  withChevron?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "text-xs py-1.5 px-3 flex items-center gap-1.5 uppercase tracking-wider font-medium rounded-md transition-colors",
        active
          ? "text-white bg-white/10"
          : "text-white/60 hover:text-white hover:bg-white/5",
      )}
    >
      {icon}
      <span>{label}</span>
      {badge && (
        <span className="ml-0.5 px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider bg-white/10 text-white/50">
          {badge}
        </span>
      )}
      {withChevron && (
        <ChevronDown
          className={cn("w-3 h-3 transition-transform duration-200", active && "rotate-180")}
        />
      )}
    </button>
  );
}

function Panel({ align, children }: { align: string; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15 }}
      className={cn(
        "absolute top-full mt-1 w-80 rounded-xl border border-white/10 bg-black/85 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden",
        align,
      )}
    >
      {children}
    </motion.div>
  );
}
