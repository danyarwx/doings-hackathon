import { useState } from "react";
import { cn } from "@/lib/utils";

export type Lang = "auto" | "de" | "en";

type Option = { value: Lang; label: string; sub: string };

const OPTIONS: Option[] = [
  { value: "auto", label: "Auto", sub: "detect" },
  { value: "de", label: "DE", sub: "German" },
  { value: "en", label: "EN", sub: "English" },
];

type Props = {
  value?: Lang;
  defaultValue?: Lang;
  onValueChange?: (v: Lang) => void;
  disabled?: boolean;
  className?: string;
};

export function LanguageSwitcher({
  value,
  defaultValue = "auto",
  onValueChange,
  disabled = false,
  className,
}: Props) {
  const [internal, setInternal] = useState<Lang>(defaultValue);
  const active = value ?? internal;

  const handle = (v: Lang) => {
    if (disabled) return;
    if (onValueChange) onValueChange(v);
    else setInternal(v);
  };

  return (
    <fieldset
      className={cn(
        "inline-flex items-center gap-0 rounded-full border border-white/10 bg-white/5 backdrop-blur-xl p-1 shadow-[0_4px_16px_rgba(0,0,0,0.4)]",
        disabled && "opacity-50",
        className,
      )}
    >
      <legend className="sr-only">Recording language</legend>
      {OPTIONS.map((opt) => {
        const selected = active === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => handle(opt.value)}
            disabled={disabled}
            title={opt.sub}
            aria-pressed={selected}
            className={cn(
              "relative px-3.5 py-1.5 rounded-full text-xs font-medium transition-colors",
              selected
                ? "bg-white/15 text-white shadow-inner"
                : "text-white/50 hover:text-white/80 hover:bg-white/5",
              disabled && "cursor-not-allowed",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </fieldset>
  );
}
