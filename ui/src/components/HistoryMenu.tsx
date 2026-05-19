import { useEffect, useRef, useState } from "react";
import { listHistory } from "../lib/api";
import type { PastSessionSummary } from "../lib/types";

type Props = {
  onSelect: (sessionId: string) => void;
};

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

export default function HistoryMenu({ onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<PastSessionSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    listHistory()
      .then(setItems)
      .catch((err) => {
        console.error(err);
        setItems([]);
      })
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="px-2.5 py-1 rounded-md text-[10px] font-medium uppercase tracking-wider text-white/60 hover:text-white hover:bg-white/10 border border-white/10"
        title="Past sessions"
      >
        History
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 max-h-80 overflow-y-auto rounded-xl border border-white/10 bg-black/80 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.6)] z-20">
          {loading && (
            <div className="px-4 py-3 text-xs text-white/40">Loading…</div>
          )}
          {!loading && items?.length === 0 && (
            <div className="px-4 py-3 text-xs text-white/40">
              No past sessions yet. Stop the current recording and start a new one to populate.
            </div>
          )}
          {!loading &&
            items?.map((s) => (
              <button
                key={s.session_id}
                onClick={() => {
                  setOpen(false);
                  onSelect(s.session_id);
                }}
                className="w-full px-4 py-2.5 text-left hover:bg-white/5 border-b border-white/5 last:border-0"
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
        </div>
      )}
    </div>
  );
}
