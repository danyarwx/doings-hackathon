import { useEffect, useRef, useState } from "react";
import type { Segment } from "../lib/types";
import GlassCard from "./GlassCard";
import HistoryMenu from "./HistoryMenu";
import SegmentCard from "./SegmentCard";

type Props = {
  segments: Segment[];
  viewingPastId?: string | null;
  onViewPast?: (id: string) => void;
  onBackToLive?: () => void;
};

export default function TranscriptPanel({
  segments,
  viewingPastId,
  onViewPast,
  onBackToLive,
}: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const isPast = !!viewingPastId;

  useEffect(() => {
    if (isPast || !autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [segments, autoScroll, isPast]);

  useEffect(() => {
    // When switching views, reset scroll to top for past, bottom for live.
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = isPast ? 0 : scrollRef.current.scrollHeight;
  }, [isPast, viewingPastId]);

  const onScroll = () => {
    if (isPast) return;
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    setAutoScroll(nearBottom);
  };

  return (
    <GlassCard className="relative flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          {isPast ? "Past Session" : "Live Transcript"}
        </h2>
        <div className="flex items-center gap-2">
          {isPast && onBackToLive && (
            <button
              onClick={onBackToLive}
              className="px-2.5 py-1 rounded-md text-[10px] font-medium uppercase tracking-wider text-neon-cyan hover:bg-neon-cyan/15 border border-neon-cyan/40"
            >
              ← Back to live
            </button>
          )}
          {!isPast && onViewPast && <HistoryMenu onSelect={onViewPast} />}
        </div>
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto px-5 py-3"
      >
        {segments.length === 0 ? (
          <div className="text-center text-white/40 py-12">
            {isPast ? "This session has no segments." : "Waiting for audio…"}
          </div>
        ) : (
          segments.map((s) => <SegmentCard key={s.id} segment={s} />)
        )}
      </div>
      {!isPast && !autoScroll && segments.length > 0 && (
        <button
          onClick={() => setAutoScroll(true)}
          className="absolute bottom-4 right-4 text-xs px-3 py-1.5 rounded-full bg-neon-blue/80 hover:bg-neon-blue text-white"
        >
          Jump to latest
        </button>
      )}
    </GlassCard>
  );
}
