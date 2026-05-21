"use client";

import React, { useRef, useState } from "react";
import { motion } from "framer-motion";

type CursorPosition = { left: number; width: number; opacity: number };

/**
 * Pill-shaped tab strip with a hover-following cursor. The original supplied
 * version was a white-on-black demo with hard-coded tabs; this version is
 * theme-inverted for our dark/glassy UI and accepts arbitrary children so
 * callers can wire their own onClick + open-state into each Tab.
 *
 * mix-blend-difference on the tab text lets a single text color invert
 * against the cursor when they overlap.
 */
export function NavHeader({ children }: { children: React.ReactNode }) {
  const [position, setPosition] = useState<CursorPosition>({
    left: 0,
    width: 0,
    opacity: 0,
  });

  return (
    <ul
      className="relative flex w-fit rounded-full border border-white/10 bg-transparent p-1"
      onMouseLeave={() => setPosition((pv) => ({ ...pv, opacity: 0 }))}
    >
      {React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child;
        return React.cloneElement(child as React.ReactElement<TabInjectedProps>, {
          __setPosition: setPosition,
        });
      })}
      <Cursor position={position} />
    </ul>
  );
}

type TabInjectedProps = {
  __setPosition?: (pos: CursorPosition) => void;
};

type NavTabProps = {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
} & TabInjectedProps;

export function NavTab({
  children,
  onClick,
  active,
  disabled,
  title,
  __setPosition,
}: NavTabProps) {
  const ref = useRef<HTMLLIElement>(null);
  return (
    <li
      ref={ref}
      title={title}
      onMouseEnter={() => {
        if (disabled || !ref.current || !__setPosition) return;
        const { width } = ref.current.getBoundingClientRect();
        __setPosition({
          width,
          opacity: 1,
          left: ref.current.offsetLeft,
        });
      }}
      onClick={disabled ? undefined : onClick}
      className={[
        "relative z-10 flex items-center gap-1.5 px-3 py-1.5 text-[11px] uppercase tracking-wider font-medium md:px-4 md:py-2 md:text-xs",
        "select-none transition-colors duration-150",
        disabled
          ? "cursor-not-allowed text-white/25"
          : "cursor-pointer text-white mix-blend-difference",
        active && !disabled ? "text-white" : "",
      ].join(" ")}
    >
      {children}
    </li>
  );
}

function Cursor({ position }: { position: CursorPosition }) {
  return (
    <motion.li
      animate={position}
      transition={{ type: "spring", stiffness: 350, damping: 30 }}
      className="absolute z-0 h-7 md:h-9 rounded-full bg-white"
    />
  );
}

export default NavHeader;
