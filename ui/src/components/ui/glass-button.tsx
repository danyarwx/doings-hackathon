import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

/**
 * Glassy pill button for primary actions (Generate / Push to Jira / etc.).
 *
 * Adapted from a supplied design that referenced non-existent CSS classes —
 * the look is reproduced here with Tailwind: translucent surface + backdrop
 * blur + soft inner highlight + soft drop shadow that responds to hover.
 */

const glassButtonVariants = cva(
  // Base: pill shape, glass surface, subtle border, inner highlight via
  // before:, soft shadow via after:, focus + hover transitions.
  [
    "group relative isolate inline-flex select-none items-center justify-center",
    "rounded-full tracking-tight",
    "border border-white/15 bg-white/10 backdrop-blur-md",
    "text-white",
    "shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_30px_rgba(0,0,0,0.45)]",
    "transition-all duration-200",
    "hover:bg-white/15 hover:border-white/25",
    "hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.24),0_12px_36px_rgba(0,0,0,0.55)]",
    "active:scale-[0.98]",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neon-cyan/50",
    "disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none",
  ].join(" "),
  {
    variants: {
      size: {
        sm: "h-8 px-4 text-xs font-medium",
        default: "h-11 px-6 text-sm font-medium",
        lg: "h-14 px-8 text-base font-semibold",
        icon: "h-10 w-10",
      },
      tone: {
        // Neutral glass (default)
        neutral: "",
        // Cyan-tinted (primary actions like Generate)
        cyan: [
          "border-neon-cyan/40 bg-neon-cyan/15 text-white",
          "hover:border-neon-cyan/60 hover:bg-neon-cyan/25",
          "shadow-[inset_0_1px_0_rgba(1,181,226,0.30),0_8px_30px_rgba(1,181,226,0.18)]",
          "hover:shadow-[inset_0_1px_0_rgba(1,181,226,0.40),0_12px_36px_rgba(1,181,226,0.30)]",
        ].join(" "),
        // Blue-tinted (push actions)
        blue: [
          "border-neon-blue/40 bg-neon-blue/15 text-white",
          "hover:border-neon-blue/60 hover:bg-neon-blue/25",
          "shadow-[inset_0_1px_0_rgba(0,117,255,0.30),0_8px_30px_rgba(0,117,255,0.18)]",
          "hover:shadow-[inset_0_1px_0_rgba(0,117,255,0.40),0_12px_36px_rgba(0,117,255,0.30)]",
        ].join(" "),
        // Pink for destructive / warnings — kept for future use
        pink: [
          "border-neon-pink/40 bg-neon-pink/15 text-white",
          "hover:border-neon-pink/60 hover:bg-neon-pink/25",
        ].join(" "),
      },
    },
    defaultVariants: {
      size: "default",
      tone: "neutral",
    },
  },
);

export interface GlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof glassButtonVariants> {
  contentClassName?: string;
}

export const GlassButton = React.forwardRef<HTMLButtonElement, GlassButtonProps>(
  ({ className, children, size, tone, contentClassName, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(glassButtonVariants({ size, tone }), className)}
        {...props}
      >
        <span className={cn("inline-flex items-center gap-2", contentClassName)}>
          {children}
        </span>
      </button>
    );
  },
);
GlassButton.displayName = "GlassButton";

export { glassButtonVariants };
