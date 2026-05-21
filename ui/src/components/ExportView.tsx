import { useMemo } from "react";
import { ArrowLeft, Download, ListChecks, Sparkles, Tag } from "lucide-react";
import type { ExportDraft, ExportRequirement } from "../lib/types";
import GlassCard from "./GlassCard";
import { cn } from "../lib/utils";

type Props = {
  draft: ExportDraft | null;
  generating: boolean;
  onGenerate: () => void;
  onBack: () => void;
  model: string;
};

const PRIORITY_CLASS = {
  high: "bg-neon-pink/15 text-neon-pink border-neon-pink/40",
  medium: "bg-neon-amber/15 text-neon-amber border-neon-amber/40",
  low: "bg-neon-cyan/15 text-neon-cyan border-neon-cyan/40",
} as const;

const ISSUETYPE_CLASS = {
  Story: "bg-neon-green/15 text-neon-green border-neon-green/40",
  Task: "bg-neon-blue/15 text-neon-blue border-neon-blue/40",
  Bug: "bg-neon-pink/15 text-neon-pink border-neon-pink/40",
  Epic: "bg-neon-amber/15 text-neon-amber border-neon-amber/40",
} as const;

const INVEST_LETTERS: Array<[keyof ExportRequirement["description"]["invest_validation"], string]> = [
  ["independent", "I"],
  ["negotiable", "N"],
  ["valuable", "V"],
  ["estimable", "E"],
  ["small", "S"],
  ["testable", "T"],
];

export default function ExportView({ draft, generating, onGenerate, onBack, model }: Props) {
  const downloadUrl = useMemo(() => {
    if (!draft) return null;
    const blob = new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" });
    return URL.createObjectURL(blob);
  }, [draft]);

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
          {draft && (
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              {draft.requirements.length} requirements · {draft.decisions.length} decisions
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {draft && downloadUrl && (
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
            {generating ? "Generating…" : draft ? "Regenerate" : "Generate"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
        {!draft && !generating && (
          <EmptyState model={model} />
        )}
        {generating && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-white/50 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-md">
              <div className="text-white/70 mb-2">Generating…</div>
              <div className="text-xs">
                Running the export pass through <span className="font-mono">{model}</span>. Cloud models finish in a few seconds; local models can take 30–120s.
              </div>
            </div>
          </div>
        )}
        {draft && (
          <>
            {draft.requirements.length === 0 && draft.decisions.length === 0 && (
              <div className="text-center text-white/40 text-sm py-12">
                The model returned no requirements or decisions. Approve a few cards on the live dashboard, then regenerate.
              </div>
            )}
            {draft.requirements.length > 0 && (
              <section className="flex flex-col gap-3">
                <h3 className="text-[10px] uppercase tracking-wider text-white/40">
                  Requirements
                </h3>
                {draft.requirements.map((r, i) => (
                  <RequirementCard key={i} req={r} />
                ))}
              </section>
            )}
            {draft.decisions.length > 0 && (
              <section className="flex flex-col gap-2">
                <h3 className="text-[10px] uppercase tracking-wider text-white/40">
                  Decisions
                </h3>
                <ul className="flex flex-col gap-1.5">
                  {draft.decisions.map((d, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/80"
                    >
                      {d.summary}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </GlassCard>
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
          on the approved insights from the just-finished session. The export will produce Jira-ready
          user stories (Given/When/Then + acceptance criteria + INVEST) and a list of decisions.
        </div>
        <div className="text-[10px] text-white/30 mt-3">
          Active model: <span className="font-mono">{model}</span>
        </div>
      </div>
    </div>
  );
}

function RequirementCard({ req }: { req: ExportRequirement }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3 flex flex-col gap-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border",
            ISSUETYPE_CLASS[req.issuetype] ?? "bg-white/10 text-white/60 border-white/20",
          )}
        >
          {req.issuetype}
        </span>
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border",
            PRIORITY_CLASS[req.priority] ?? "bg-white/10 text-white/60 border-white/20",
          )}
        >
          {req.priority}
        </span>
        {req.story_points != null && (
          <span className="px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider text-white/60 border border-white/10">
            {req.story_points} pts
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {INVEST_LETTERS.map(([key, letter]) => {
            const ok = req.description.invest_validation?.[key];
            return (
              <span
                key={key}
                title={key}
                className={cn(
                  "w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center border",
                  ok
                    ? "bg-neon-green/15 text-neon-green border-neon-green/40"
                    : "bg-white/5 text-white/30 border-white/10",
                )}
              >
                {letter}
              </span>
            );
          })}
        </div>
      </div>

      <h4 className="text-sm text-white font-medium leading-snug">{req.summary}</h4>

      <div className="text-xs leading-relaxed grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
        <span className="text-white/40 font-semibold">Given</span>
        <span className="text-white/80">{req.description.user_story.given}</span>
        <span className="text-white/40 font-semibold">When</span>
        <span className="text-white/80">{req.description.user_story.when}</span>
        <span className="text-white/40 font-semibold">Then</span>
        <span className="text-white/80">{req.description.user_story.then}</span>
      </div>

      {req.description.acceptance_criteria.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-white/40 mb-1">
            <ListChecks className="w-3 h-3" /> Acceptance criteria
          </div>
          <ul className="flex flex-col gap-0.5 text-xs text-white/70 list-disc pl-5">
            {req.description.acceptance_criteria.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {req.labels.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Tag className="w-3 h-3 text-white/30" />
          {req.labels.map((l, i) => (
            <span
              key={i}
              className="px-1.5 py-0.5 rounded text-[10px] text-white/60 border border-white/10"
            >
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
