import GlassCard from "./GlassCard";

export default function InsightsPanel() {
  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          AI Insights
        </h2>
      </div>
      <div className="flex-1 flex items-center justify-center px-5 py-3">
        <div className="text-center text-white/40 text-sm border border-dashed border-white/20 rounded-xl p-6">
          AI insights will appear here when Step 3 is wired up.
        </div>
      </div>
    </GlassCard>
  );
}
