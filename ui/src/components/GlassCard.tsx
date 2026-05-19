import type { PropsWithChildren } from "react";

type Props = PropsWithChildren<{ className?: string }>;

export default function GlassCard({ children, className = "" }: Props) {
  return (
    <div
      className={
        "rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl " +
        "shadow-[0_8px_32px_rgba(0,0,0,0.4)] " +
        className
      }
    >
      {children}
    </div>
  );
}
