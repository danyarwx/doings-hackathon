import { useState } from "react";
import { approveInsight, declineInsight, editInsight } from "../lib/api";
import type { Insight } from "../lib/types";
import { cn } from "../lib/utils";

type Props = { insight: Insight };

export default function InsightCard({ insight }: Props) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(insight.text);
  const [quoteOpen, setQuoteOpen] = useState(false);

  const acted = insight.status !== "pending";
  const detail = insight.detail?.trim() || "";
  const quote = insight.source_quote?.trim() || "";

  const run = async (fn: () => Promise<unknown>) => {
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

  const handleEditOpen = () => {
    setDraft(insight.text);
    setEditing(true);
  };

  const handleEditSave = () =>
    run(async () => {
      const t = draft.trim();
      if (!t) return;
      await editInsight(insight.id, t);
      setEditing(false);
    });

  return (
    <div
      className={cn(
        "rounded-xl border border-white/10 bg-white/5 p-3 transition-opacity",
        insight.status === "declined" && "opacity-40",
      )}
    >
      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full text-sm bg-black/40 border border-white/10 rounded-md px-2 py-1.5 text-white focus:outline-none focus:border-neon-cyan/60"
        />
      ) : (
        <p className="text-sm text-white leading-snug">{insight.text}</p>
      )}

      {!editing && (detail || quote) && (
        <div className="mt-1.5">
          {detail && (
            <p className="text-xs text-white/50 leading-snug">{detail}</p>
          )}
          {quote && (
            <>
              <button
                onClick={() => setQuoteOpen((v) => !v)}
                className="mt-1 text-[10px] text-white/30 hover:text-white/60 uppercase tracking-wider"
              >
                {quoteOpen ? "▾ Hide source" : "▸ Show source"}
              </button>
              {quoteOpen && (
                <p className="mt-1 text-xs text-white/35 italic leading-snug">
                  “{quote}”
                </p>
              )}
            </>
          )}
        </div>
      )}

      {!acted && !editing && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => run(() => approveInsight(insight.id))}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-green/15 text-neon-green border border-neon-green/30 hover:bg-neon-green/25 disabled:opacity-50"
          >
            ✓ Approve
          </button>
          <button
            onClick={handleEditOpen}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-white/10 text-white border border-white/20 hover:bg-white/15 disabled:opacity-50"
          >
            ✎ Edit
          </button>
          <button
            onClick={() => run(() => declineInsight(insight.id))}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-pink/15 text-neon-pink border border-neon-pink/30 hover:bg-neon-pink/25 disabled:opacity-50"
          >
            ✗ Decline
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={handleEditSave}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/30 hover:bg-neon-cyan/25 disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={busy}
            className="flex-1 py-1.5 rounded-md text-xs font-medium bg-white/10 text-white/70 border border-white/20 hover:bg-white/15 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}

      {acted && !editing && (
        <p className="mt-2 text-[10px] text-white/40 uppercase tracking-wider">
          {insight.status}
        </p>
      )}
    </div>
  );
}
