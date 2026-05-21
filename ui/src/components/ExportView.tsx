import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  ListChecks,
  Plus,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import type {
  ExportDecision,
  ExportDraft,
  ExportRequirement,
  InvestValidation,
} from "../lib/types";
import {
  getJiraConfig,
  pushExportAll,
  pushExportItem,
  updateExport,
} from "../lib/api";
import type { JiraConfig, JiraPushAllRow } from "../lib/api";
import GlassCard from "./GlassCard";
import JiraConfigDrawer from "./JiraConfigDrawer";
import { cn } from "../lib/utils";

type Props = {
  draft: ExportDraft | null;
  generating: boolean;
  onGenerate: () => void;
  onBack: () => void;
  model: string;
};

const ISSUETYPES: ExportRequirement["issuetype"][] = ["Story", "Task", "Bug", "Epic"];
const PRIORITIES: ExportRequirement["priority"][] = ["high", "medium", "low"];

const PRIORITY_CLASS = {
  high: "text-neon-pink border-neon-pink/40",
  medium: "text-neon-amber border-neon-amber/40",
  low: "text-neon-cyan border-neon-cyan/40",
} as const;

const ISSUETYPE_CLASS = {
  Story: "text-neon-green border-neon-green/40",
  Task: "text-neon-blue border-neon-blue/40",
  Bug: "text-neon-pink border-neon-pink/40",
  Epic: "text-neon-amber border-neon-amber/40",
} as const;

const INVEST_LETTERS: Array<[keyof InvestValidation, string]> = [
  ["independent", "I"],
  ["negotiable", "N"],
  ["valuable", "V"],
  ["estimable", "E"],
  ["small", "S"],
  ["testable", "T"],
];

const EMPTY_INVEST: InvestValidation = {
  independent: true,
  negotiable: true,
  valuable: true,
  estimable: true,
  small: true,
  testable: true,
};

const newRequirement = (): ExportRequirement => ({
  issuetype: "Story",
  summary: "",
  description: {
    user_story: { given: "", when: "", then: "" },
    acceptance_criteria: [],
    invest_validation: { ...EMPTY_INVEST },
  },
  priority: "medium",
  labels: [],
  story_points: null,
});

export default function ExportView({
  draft,
  generating,
  onGenerate,
  onBack,
  model,
}: Props) {
  const [local, setLocal] = useState<ExportDraft | null>(draft);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const lastSavedRef = useRef<string>("");

  // Jira state
  const [jiraConfig, setJiraConfig] = useState<JiraConfig>({
    url_set: false, email_set: false, token_set: false, project_set: false,
    url: "", project: "",
  });
  const [pushingIdx, setPushingIdx] = useState<number | null>(null);
  const [pushingAll, setPushingAll] = useState(false);
  // Track pushed results per requirement index → key/url or error.
  const [pushedKeys, setPushedKeys] = useState<Record<number, { key?: string; url?: string; error?: string }>>({});

  useEffect(() => {
    getJiraConfig().then(setJiraConfig).catch(() => {});
  }, []);

  const jiraReady =
    jiraConfig.url_set && jiraConfig.email_set && jiraConfig.token_set && jiraConfig.project_set;

  // Sync local copy when a new draft arrives (e.g. via WS or initial fetch).
  useEffect(() => {
    if (draft) {
      setLocal(draft);
      lastSavedRef.current = JSON.stringify(draft);
    } else {
      setLocal(null);
      lastSavedRef.current = "";
    }
  }, [draft]);

  // Debounced autosave to backend whenever the local draft diverges.
  useEffect(() => {
    if (!local) return;
    const serialized = JSON.stringify(local);
    if (serialized === lastSavedRef.current) return;
    setSaveState("saving");
    const t = setTimeout(() => {
      updateExport(local)
        .then(() => {
          lastSavedRef.current = serialized;
          setSaveState("saved");
        })
        .catch((err) => {
          console.error(err);
          setSaveState("error");
        });
    }, 500);
    return () => clearTimeout(t);
  }, [local]);

  const downloadUrl = useMemo(() => {
    if (!local) return null;
    const blob = new Blob([JSON.stringify(local, null, 2)], { type: "application/json" });
    return URL.createObjectURL(blob);
  }, [local]);

  const updateRequirement = useCallback(
    (idx: number, patch: Partial<ExportRequirement>) => {
      setLocal((prev) => {
        if (!prev) return prev;
        const next = { ...prev, requirements: prev.requirements.slice() };
        next.requirements[idx] = { ...next.requirements[idx], ...patch };
        return next;
      });
    },
    [],
  );

  const removeRequirement = useCallback((idx: number) => {
    setLocal((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        requirements: prev.requirements.filter((_, i) => i !== idx),
      };
    });
  }, []);

  const addRequirement = useCallback(() => {
    setLocal((prev) => {
      if (!prev) return prev;
      return { ...prev, requirements: [...prev.requirements, newRequirement()] };
    });
  }, []);

  const updateDecision = useCallback((idx: number, summary: string) => {
    setLocal((prev) => {
      if (!prev) return prev;
      const next = { ...prev, decisions: prev.decisions.slice() };
      next.decisions[idx] = { summary };
      return next;
    });
  }, []);

  const removeDecision = useCallback((idx: number) => {
    setLocal((prev) => {
      if (!prev) return prev;
      return { ...prev, decisions: prev.decisions.filter((_, i) => i !== idx) };
    });
  }, []);

  const addDecision = useCallback(() => {
    setLocal((prev) => {
      if (!prev) return prev;
      return { ...prev, decisions: [...prev.decisions, { summary: "" }] };
    });
  }, []);

  const handlePushOne = async (idx: number) => {
    if (pushingIdx !== null || pushingAll || !jiraReady) return;
    setPushingIdx(idx);
    setPushedKeys((prev) => ({ ...prev, [idx]: {} }));
    try {
      const result = await pushExportItem(idx);
      setPushedKeys((prev) => ({ ...prev, [idx]: { key: result.key, url: result.url } }));
    } catch (err) {
      console.error(err);
      setPushedKeys((prev) => ({ ...prev, [idx]: { error: String(err) } }));
    } finally {
      setPushingIdx(null);
    }
  };

  const handlePushAll = async () => {
    if (pushingAll || pushingIdx !== null || !jiraReady) return;
    setPushingAll(true);
    try {
      const results: JiraPushAllRow[] = await pushExportAll();
      const next: Record<number, { key?: string; url?: string; error?: string }> = {};
      for (const row of results) {
        next[row.index] = row.error
          ? { error: row.error }
          : { key: row.key, url: row.url };
      }
      setPushedKeys(next);
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setPushingAll(false);
    }
  };

  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-[11px] text-white/60 hover:text-white uppercase tracking-wider"
          >
            <ArrowLeft className="w-3 h-3" /> Back
          </button>
          <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
            Export
          </h2>
          {local && (
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              {local.requirements.length} requirements · {local.decisions.length} decisions
            </span>
          )}
          <SaveIndicator state={saveState} />
        </div>
        <div className="flex items-center gap-2">
          {local && local.requirements.length > 0 && (
            <button
              onClick={handlePushAll}
              disabled={!jiraReady || pushingAll || pushingIdx !== null}
              title={jiraReady ? "Push every requirement to Jira" : "Configure Jira below first"}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-medium uppercase tracking-wider border",
                jiraReady
                  ? "text-neon-blue bg-neon-blue/10 border-neon-blue/40 hover:bg-neon-blue/20"
                  : "text-white/30 bg-white/5 border-white/10 cursor-not-allowed",
                (pushingAll || pushingIdx !== null) && "opacity-50 cursor-not-allowed",
              )}
            >
              <Upload className="w-3 h-3" />
              {pushingAll ? "Pushing…" : "Push all to Jira"}
            </button>
          )}
          {local && downloadUrl && (
            <a
              href={downloadUrl}
              download={`doings-export-${Date.now()}.json`}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] uppercase tracking-wider text-white/60 hover:text-white hover:bg-white/5 border border-white/10"
            >
              <Download className="w-3 h-3" /> Download JSON
            </a>
          )}
          <button
            onClick={onGenerate}
            disabled={generating}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-medium uppercase tracking-wider border",
              "text-neon-cyan bg-neon-cyan/10 border-neon-cyan/40 hover:bg-neon-cyan/20",
              generating && "opacity-50 cursor-not-allowed",
            )}
          >
            <Sparkles className="w-3 h-3" />
            {generating ? "Generating…" : local ? "Regenerate" : "Generate"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
        {!local && !generating && <EmptyState model={model} />}
        {generating && <GeneratingState model={model} />}
        {local && (
          <>
            <JiraConfigDrawer config={jiraConfig} onChange={setJiraConfig} />

            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="text-[10px] uppercase tracking-wider text-white/40">
                  Requirements
                </h3>
                <button
                  onClick={addRequirement}
                  className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-white/50 hover:text-white"
                >
                  <Plus className="w-3 h-3" /> Add
                </button>
              </div>
              {local.requirements.length === 0 && (
                <div className="text-center text-white/30 text-xs py-6 border border-dashed border-white/10 rounded-xl">
                  No requirements yet. Click <span className="text-white/60">Add</span> or regenerate.
                </div>
              )}
              {local.requirements.map((r, i) => (
                <EditableRequirement
                  key={i}
                  req={r}
                  pushedStatus={pushedKeys[i]}
                  pushing={pushingIdx === i || pushingAll}
                  jiraReady={jiraReady}
                  onChange={(patch) => updateRequirement(i, patch)}
                  onRemove={() => removeRequirement(i)}
                  onPush={() => handlePushOne(i)}
                />
              ))}
            </section>

            <section className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <h3 className="text-[10px] uppercase tracking-wider text-white/40">
                  Decisions
                </h3>
                <button
                  onClick={addDecision}
                  className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-white/50 hover:text-white"
                >
                  <Plus className="w-3 h-3" /> Add
                </button>
              </div>
              {local.decisions.length === 0 && (
                <div className="text-center text-white/30 text-xs py-4 border border-dashed border-white/10 rounded-xl">
                  No decisions.
                </div>
              )}
              {local.decisions.map((d, i) => (
                <EditableDecision
                  key={i}
                  decision={d}
                  onChange={(s) => updateDecision(i, s)}
                  onRemove={() => removeDecision(i)}
                />
              ))}
            </section>
          </>
        )}
      </div>
    </GlassCard>
  );
}

function SaveIndicator({ state }: { state: "idle" | "saving" | "saved" | "error" }) {
  if (state === "idle") return null;
  const label =
    state === "saving" ? "Saving…" : state === "saved" ? "Saved" : "Save error";
  const cls =
    state === "saving"
      ? "text-white/40"
      : state === "saved"
        ? "text-neon-green"
        : "text-neon-pink";
  return (
    <span className={cn("text-[10px] uppercase tracking-wider", cls)}>{label}</span>
  );
}

function EmptyState({ model }: { model: string }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center text-white/40 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-md">
        <div className="text-white/60 mb-2 flex items-center justify-center gap-1.5">
          <Sparkles className="w-4 h-4" /> Ready to generate
        </div>
        <div className="text-xs leading-relaxed">
          Click <span className="text-white/70 font-medium">Generate</span> to run a post-meeting pass
          on the approved insights from the just-finished session. You'll get Jira-ready user
          stories (Given/When/Then + acceptance criteria + INVEST) and a list of decisions, all
          editable inline.
        </div>
        <div className="text-[10px] text-white/30 mt-3">
          Active model: <span className="font-mono">{model}</span>
        </div>
      </div>
    </div>
  );
}

function GeneratingState({ model }: { model: string }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center text-white/50 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-md">
        <div className="text-white/70 mb-2">Generating…</div>
        <div className="text-xs">
          Running the export pass through <span className="font-mono">{model}</span>. Cloud models
          finish in a few seconds; local models can take 30–120s.
        </div>
      </div>
    </div>
  );
}

function EditableRequirement({
  req,
  onChange,
  onRemove,
  onPush,
  pushedStatus,
  pushing,
  jiraReady,
}: {
  req: ExportRequirement;
  onChange: (patch: Partial<ExportRequirement>) => void;
  onRemove: () => void;
  onPush: () => void;
  pushedStatus?: { key?: string; url?: string; error?: string };
  pushing: boolean;
  jiraReady: boolean;
}) {
  const story = req.description.user_story;
  const ac = req.description.acceptance_criteria;
  const invest = req.description.invest_validation;

  const updateStory = (field: "given" | "when" | "then", value: string) =>
    onChange({
      description: { ...req.description, user_story: { ...story, [field]: value } },
    });

  const updateAcAt = (i: number, value: string) => {
    const next = ac.slice();
    next[i] = value;
    onChange({ description: { ...req.description, acceptance_criteria: next } });
  };

  const addAc = () =>
    onChange({ description: { ...req.description, acceptance_criteria: [...ac, ""] } });

  const removeAc = (i: number) =>
    onChange({
      description: {
        ...req.description,
        acceptance_criteria: ac.filter((_, idx) => idx !== i),
      },
    });

  const toggleInvest = (key: keyof InvestValidation) =>
    onChange({
      description: {
        ...req.description,
        invest_validation: { ...invest, [key]: !invest[key] },
      },
    });

  const removeLabel = (i: number) =>
    onChange({ labels: req.labels.filter((_, idx) => idx !== i) });

  const addLabel = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || req.labels.includes(trimmed)) return;
    onChange({ labels: [...req.labels, trimmed] });
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3 flex flex-col gap-3">
      {/* Header row: type + priority + story points + INVEST + delete */}
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={req.issuetype}
          onChange={(e) => onChange({ issuetype: e.target.value as ExportRequirement["issuetype"] })}
          className={cn(
            "bg-transparent text-[10px] font-semibold uppercase tracking-wider border rounded-md px-2 py-0.5",
            ISSUETYPE_CLASS[req.issuetype],
          )}
        >
          {ISSUETYPES.map((t) => (
            <option key={t} value={t} className="bg-black text-white">{t}</option>
          ))}
        </select>
        <select
          value={req.priority}
          onChange={(e) => onChange({ priority: e.target.value as ExportRequirement["priority"] })}
          className={cn(
            "bg-transparent text-[10px] font-semibold uppercase tracking-wider border rounded-md px-2 py-0.5",
            PRIORITY_CLASS[req.priority],
          )}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p} className="bg-black text-white">{p}</option>
          ))}
        </select>
        <div className="flex items-center gap-1 text-[10px] text-white/50">
          <input
            type="number"
            min={0}
            value={req.story_points ?? ""}
            onChange={(e) =>
              onChange({ story_points: e.target.value === "" ? null : Number(e.target.value) })
            }
            placeholder="pts"
            className="w-12 bg-transparent border border-white/10 rounded px-1.5 py-0.5 text-white/80 text-[10px] focus:outline-none focus:border-neon-cyan/60"
          />
          <span>pts</span>
        </div>
        <div className="ml-auto flex items-center gap-1">
          {INVEST_LETTERS.map(([key, letter]) => {
            const ok = !!invest?.[key];
            return (
              <button
                key={key}
                type="button"
                title={key}
                onClick={() => toggleInvest(key)}
                className={cn(
                  "w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center border transition-colors",
                  ok
                    ? "bg-neon-green/15 text-neon-green border-neon-green/40"
                    : "bg-white/5 text-white/30 border-white/10 hover:bg-white/10",
                )}
              >
                {letter}
              </button>
            );
          })}
          <button
            onClick={onRemove}
            title="Remove requirement"
            className="ml-1 w-6 h-6 rounded-md text-white/40 hover:text-neon-pink hover:bg-neon-pink/10 flex items-center justify-center"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Summary */}
      <input
        value={req.summary}
        onChange={(e) => onChange({ summary: e.target.value })}
        placeholder="Concise Jira-friendly summary"
        className="w-full text-sm text-white bg-transparent border border-white/10 rounded-md px-2 py-1.5 focus:outline-none focus:border-neon-cyan/60 font-medium"
      />

      {/* User story */}
      <div className="grid grid-cols-[64px_1fr] gap-x-2 gap-y-1.5">
        {(["given", "when", "then"] as const).map((field) => (
          <FieldRow
            key={field}
            label={field}
            value={story[field]}
            onChange={(v) => updateStory(field, v)}
          />
        ))}
      </div>

      {/* Acceptance criteria */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-white/40">
            <ListChecks className="w-3 h-3" /> Acceptance criteria
          </div>
          <button
            onClick={addAc}
            className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-white/50 hover:text-white"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        <div className="flex flex-col gap-1.5">
          {ac.length === 0 && (
            <div className="text-[10px] text-white/30 italic">No acceptance criteria yet.</div>
          )}
          {ac.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={c}
                onChange={(e) => updateAcAt(i, e.target.value)}
                placeholder="Specific, testable, observable behavior"
                className="flex-1 text-xs text-white/80 bg-transparent border border-white/10 rounded-md px-2 py-1 focus:outline-none focus:border-neon-cyan/60"
              />
              <button
                onClick={() => removeAc(i)}
                className="text-white/40 hover:text-neon-pink"
                title="Remove criterion"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Labels */}
      <LabelChips labels={req.labels} onRemove={removeLabel} onAdd={addLabel} />

      {/* Jira push row */}
      <div className="flex items-center justify-between pt-1 border-t border-white/5">
        <div className="text-[11px] text-white/50">
          {pushedStatus?.key && (
            <span className="flex items-center gap-1 text-neon-green">
              Pushed:
              <a
                href={pushedStatus.url ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-neon-green hover:underline flex items-center gap-1"
              >
                {pushedStatus.key}
                <ExternalLink className="w-3 h-3" />
              </a>
            </span>
          )}
          {pushedStatus?.error && (
            <span className="text-neon-pink">Error: {pushedStatus.error}</span>
          )}
          {!pushedStatus && !jiraReady && (
            <span className="text-white/30">Configure Jira above to push</span>
          )}
        </div>
        <button
          onClick={onPush}
          disabled={!jiraReady || pushing || !!pushedStatus?.key}
          title={pushedStatus?.key ? "Already pushed" : "Create Jira issue from this requirement"}
          className={cn(
            "flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-medium uppercase tracking-wider border",
            jiraReady && !pushedStatus?.key
              ? "text-neon-blue bg-neon-blue/10 border-neon-blue/40 hover:bg-neon-blue/20"
              : "text-white/30 bg-white/5 border-white/10 cursor-not-allowed",
            pushing && "opacity-60 cursor-wait",
          )}
        >
          <Upload className="w-3 h-3" />
          {pushing ? "Pushing…" : pushedStatus?.key ? "Pushed" : "Push to Jira"}
        </button>
      </div>
    </div>
  );
}

function FieldRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <>
      <span className="text-[10px] uppercase tracking-wider text-white/40 font-semibold pt-1.5">
        {label}
      </span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        className="text-xs text-white/80 bg-transparent border border-white/10 rounded-md px-2 py-1 focus:outline-none focus:border-neon-cyan/60 resize-none"
      />
    </>
  );
}

function LabelChips({
  labels,
  onAdd,
  onRemove,
}: {
  labels: string[];
  onAdd: (text: string) => void;
  onRemove: (i: number) => void;
}) {
  const [draft, setDraft] = useState("");
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Tag className="w-3 h-3 text-white/30" />
      {labels.map((l, i) => (
        <span
          key={i}
          className="px-1.5 py-0.5 rounded text-[10px] text-white/60 border border-white/10 flex items-center gap-1"
        >
          {l}
          <button
            onClick={() => onRemove(i)}
            className="text-white/30 hover:text-neon-pink"
            title="Remove label"
          >
            <X className="w-2.5 h-2.5" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            onAdd(draft);
            setDraft("");
          }
        }}
        onBlur={() => {
          if (draft.trim()) {
            onAdd(draft);
            setDraft("");
          }
        }}
        placeholder="add label"
        className="bg-transparent text-[10px] text-white/60 placeholder:text-white/25 focus:outline-none px-1 w-24"
      />
    </div>
  );
}

function EditableDecision({
  decision,
  onChange,
  onRemove,
}: {
  decision: ExportDecision;
  onChange: (s: string) => void;
  onRemove: () => void;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 flex items-center gap-2">
      <input
        value={decision.summary}
        onChange={(e) => onChange(e.target.value)}
        placeholder="What was decided?"
        className="flex-1 text-xs text-white/80 bg-transparent border-none px-1 py-1 focus:outline-none"
      />
      <button
        onClick={onRemove}
        className="text-white/40 hover:text-neon-pink"
        title="Remove decision"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
