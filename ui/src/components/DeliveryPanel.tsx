import type { DeliveryStatus } from "../lib/types";
import GlassCard from "./GlassCard";

function icon(status: DeliveryStatus["status"]): { glyph: string; cls: string } {
  if (status === "delivered") return { glyph: "✓", cls: "text-neon-green" };
  if (status === "failed") return { glyph: "✗", cls: "text-neon-pink" };
  return { glyph: "⟳", cls: "text-neon-amber animate-spin-slow" };
}

export default function DeliveryPanel({
  deliveries,
}: {
  deliveries: Map<string, DeliveryStatus>;
}) {
  const rows = Array.from(deliveries.values()).sort((a, b) =>
    b.id.localeCompare(a.id),
  );

  return (
    <GlassCard className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          Delivery Status
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3">
        {rows.length === 0 ? (
          <div className="text-center text-white/40 py-8 text-sm">
            No deliveries yet.
          </div>
        ) : (
          rows.map((d) => {
            const { glyph, cls } = icon(d.status);
            return (
              <div
                key={d.id}
                className="flex items-center justify-between py-1.5 text-sm"
              >
                <span className="font-mono text-white/70">{d.id}</span>
                <span className={`text-lg ${cls}`}>{glyph}</span>
              </div>
            );
          })
        )}
      </div>
    </GlassCard>
  );
}
