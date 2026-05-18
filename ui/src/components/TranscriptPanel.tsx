import { useEffect, useRef, useState } from "react";
import type { Segment } from "../lib/types";
import GlassCard from "./GlassCard";
import SegmentCard from "./SegmentCard";

export default function TranscriptPanel({ segments }: { segments: Segment[] }) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [segments, autoScroll]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    setAutoScroll(nearBottom);
  };

  return (
    <GlassCard className="relative flex flex-col h-full overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10">
        <h2 className="text-sm font-medium text-white/70 tracking-wider uppercase">
          Live Transcript
        </h2>
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto px-5 py-3"
      >
        {segments.length === 0 ? (
          <div className="text-center text-white/40 py-12">
            Waiting for audio…
          </div>
        ) : (
          segments.map((s) => <SegmentCard key={s.id} segment={s} />)
        )}
      </div>
      {!autoScroll && segments.length > 0 && (
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
