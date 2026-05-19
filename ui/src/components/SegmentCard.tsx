import type { Segment } from "../lib/types";

function fmtTs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
}

function langClass(lang: string): string {
  if (lang === "de") return "bg-neon-pink/20 text-neon-pink border-neon-pink/40";
  if (lang === "en") return "bg-neon-cyan/20 text-neon-cyan border-neon-cyan/40";
  return "bg-neon-blue/20 text-neon-blue border-neon-blue/40";
}

export default function SegmentCard({ segment }: { segment: Segment }) {
  return (
    <div className="flex gap-3 py-2 text-sm">
      <span className="text-white/40 font-mono shrink-0 w-20">
        [{fmtTs(segment.start_s)}]
      </span>
      <span
        className={
          "px-2 py-0.5 rounded-md text-xs font-medium border h-fit shrink-0 " +
          langClass(segment.lang)
        }
      >
        {segment.lang.toUpperCase()}
      </span>
      <span className="text-white leading-relaxed">{segment.text}</span>
    </div>
  );
}
