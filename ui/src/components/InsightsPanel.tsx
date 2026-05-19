import type { AiStatus, Insight } from "../lib/types";
import GlassCard from "./GlassCard";
import InsightCard from "./InsightCard";

type Props = {
  insights: Insight[];
  aiStatus: AiStatus;
};

const STATUS_DOT: Record<AiStatus, string> = {
  ok: "bg-neon-green",
  no_model: "bg-neon-amber",
  offline: "bg-neon-pink",
  unknown: "bg-white/30",
};

const STATUS_LABEL: Record<AiStatus, string> = {
  ok: "AI online",
  no_model: "Model not pulled",
  offline: "AI offline",
  unknown: "AI status unknown",
};

function emptyCopy(status: AiStatus): { title: string; sub: string } {
  if (status === "offline") {
    return {
      title: "AI offline",
      sub: "Start Ollama (`ollama serve`) and the panel will start populating.",
    };
  }
  if (status === "no_model") {
    return {
      title: "Model not installed",
      sub: "Run `ollama pull phi3` (or whichever model OLLAMA_MODEL points at) and try again.",
    };
  }
  return {
    title: "No requirements yet",
    sub: "Speak about what the system should do; requirements will appear here.",
  };
}

export default function InsightsPanel({ insights, aiStatus }: Props) {
  const pending = insights.filter((i) => i.status === "pending").length;
  const empty = emptyCopy(aiStatus);

  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          AI Insights
        </h2>
        <div className="flex items-center gap-3">
          {insights.length > 0 && (
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              {pending} pending
            </span>
          )}
          <span
            className="flex items-center gap-1.5 text-[10px] text-white/60 uppercase tracking-wider"
            title={STATUS_LABEL[aiStatus]}
          >
            <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[aiStatus]}`} />
            {aiStatus}
          </span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-2">
        {insights.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-white/40 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-xs">
              <div className="text-white/60 mb-2">{empty.title}</div>
              <div className="text-xs">{empty.sub}</div>
            </div>
          </div>
        ) : (
          insights.map((insight) => <InsightCard key={insight.id} insight={insight} />)
        )}
      </div>
    </GlassCard>
  );
}
