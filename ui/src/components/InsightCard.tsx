import type { Insight, InsightType } from "../lib/types";
import { cn } from "../lib/utils";

type Props = {
  insight: Insight;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
};

const TYPE_LABEL: Record<InsightType, string> = {
  requirement: "Requirement",
  action_item: "Action item",
  decision: "Decision",
  chatter: "Chatter",
};

const TYPE_CLASS: Record<InsightType, string> = {
  requirement: "bg-neon-cyan/15 text-neon-cyan border-neon-cyan/40",
  action_item: "bg-neon-amber/15 text-neon-amber border-neon-amber/40",
  decision: "bg-neon-green/15 text-neon-green border-neon-green/40",
  chatter: "bg-white/10 text-white/50 border-white/20",
};

export default function InsightCard({ insight, onApprove, onReject }: Props) {
  const acted = insight.status !== "pending";

  return (
    <div
      className={cn(
        "rounded-xl border border-white/10 bg-white/5 p-3 transition-opacity",
        acted && "opacity-50",
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span
          className={cn(
            "px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border",
            TYPE_CLASS[insight.type],
          )}
        >
          {TYPE_LABEL[insight.type]}
        </span>
        {insight.needs_review && (
          <span className="text-[10px] text-neon-amber/80 uppercase tracking-wider">
            needs review
          </span>
        )}
        <span className="text-[10px] text-white/30 ml-auto tabular-nums">
          {(insight.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <p className="text-sm text-white leading-snug">{insight.text}</p>
      {insight.source_quote && (
        <p className="mt-1.5 text-xs text-white/40 italic leading-snug">
          “{insight.source_quote}”
        </p>
      )}
      {!acted && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => onApprove?.(insight.id)}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-green/15 text-neon-green border border-neon-green/30 hover:bg-neon-green/25 transition-colors"
          >
            ✓ Approve
          </button>
          <button
            onClick={() => onReject?.(insight.id)}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-pink/15 text-neon-pink border border-neon-pink/30 hover:bg-neon-pink/25 transition-colors"
          >
            ✗ Reject
          </button>
        </div>
      )}
      {acted && (
        <p className="mt-2 text-[10px] text-white/40 uppercase tracking-wider">
          {insight.status}
        </p>
      )}
    </div>
  );
}
