import { useState } from "react";
import type { Insight } from "../lib/types";
import GlassCard from "./GlassCard";
import InsightCard from "./InsightCard";

type Props = { insights?: Insight[] };

export default function InsightsPanel({ insights = [] }: Props) {
  // Local state lets the scaffold demo approve/reject before Step 3 wires
  // up backend-pushed insights. Replace with backend-driven mutation later.
  const [items, setItems] = useState<Insight[]>(insights);

  const setStatus = (id: string, status: "approved" | "rejected") => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status } : i)));
  };

  const hasItems = items.length > 0;
  const pendingCount = items.filter((i) => i.status === "pending").length;

  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          AI Insights
        </h2>
        {hasItems && (
          <span className="text-[10px] text-white/40 uppercase tracking-wider">
            {pendingCount} pending
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-2">
        {!hasItems ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-white/40 text-sm border border-dashed border-white/20 rounded-xl p-6 max-w-xs">
              <div className="text-white/60 mb-2">No insights yet</div>
              <div className="text-xs">
                The local LLM will extract requirements, decisions, and action items here as you speak (Step 3).
              </div>
            </div>
          </div>
        ) : (
          items.map((insight) => (
            <InsightCard
              key={insight.id}
              insight={insight}
              onApprove={(id) => setStatus(id, "approved")}
              onReject={(id) => setStatus(id, "rejected")}
            />
          ))
        )}
      </div>
    </GlassCard>
  );
}
