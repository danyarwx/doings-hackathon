import { useState } from "react";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";

export type NavItem = {
  id: number;
  label: string;
  subMenus?: {
    title: string;
    items: {
      label: string;
      description: string;
      icon: React.ElementType;
      onClick?: () => void;
    }[];
  }[];
  link?: string;
  onClick?: () => void;
  disabled?: boolean;
  badge?: string;
};

type Props = {
  navItems: NavItem[];
};

export function DropdownNavigation({ navItems }: Props) {
  const [openMenu, setOpenMenu] = React.useState<string | null>(null);
  const [isHover, setIsHover] = useState<number | null>(null);

  return (
    <ul className="relative flex items-center space-x-0">
      {navItems.map((navItem) => (
        <li
          key={navItem.label}
          className="relative"
          onMouseEnter={() => setOpenMenu(navItem.label)}
          onMouseLeave={() => setOpenMenu(null)}
        >
          <button
            disabled={navItem.disabled}
            onClick={navItem.onClick}
            className={`text-xs py-1.5 px-3 flex group transition-colors duration-300 items-center justify-center gap-1 relative uppercase tracking-wider font-medium ${
              navItem.disabled
                ? "cursor-not-allowed text-white/25"
                : "cursor-pointer text-white/60 hover:text-white"
            }`}
            onMouseEnter={() => setIsHover(navItem.id)}
            onMouseLeave={() => setIsHover(null)}
          >
            <span>{navItem.label}</span>
            {navItem.badge && (
              <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider bg-white/10 text-white/50">
                {navItem.badge}
              </span>
            )}
            {navItem.subMenus && !navItem.disabled && (
              <ChevronDown
                className={`h-3 w-3 group-hover:rotate-180 duration-300 transition-transform ${
                  openMenu === navItem.label ? "rotate-180" : ""
                }`}
              />
            )}
            {!navItem.disabled &&
              (isHover === navItem.id || openMenu === navItem.label) && (
                <motion.div
                  layoutId="hover-bg"
                  className="absolute inset-0 size-full bg-white/5"
                  style={{ borderRadius: 8 }}
                />
              )}
          </button>

          <AnimatePresence>
            {openMenu === navItem.label && navItem.subMenus && (
              <div className="w-auto absolute left-0 top-full pt-2 z-30">
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.15 }}
                  className="border border-white/10 bg-black/80 backdrop-blur-xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)]"
                  style={{ borderRadius: 16 }}
                >
                  <div className="w-fit shrink-0 flex space-x-9 overflow-hidden">
                    {navItem.subMenus.map((sub) => (
                      <div className="w-full" key={sub.title}>
                        <h3 className="mb-3 text-[10px] font-medium uppercase tracking-wider text-white/40">
                          {sub.title}
                        </h3>
                        <ul className="space-y-3">
                          {sub.items.map((item) => {
                            const Icon = item.icon;
                            return (
                              <li key={item.label}>
                                <button
                                  onClick={item.onClick}
                                  className="w-full text-left flex items-start space-x-3 group"
                                >
                                  <div className="border border-white/10 text-white/70 rounded-md flex items-center justify-center size-9 shrink-0 group-hover:bg-white/10 group-hover:text-white transition-colors duration-300">
                                    <Icon className="h-4 w-4 flex-none" />
                                  </div>
                                  <div className="leading-tight w-max">
                                    <p className="text-xs font-medium text-white">
                                      {item.label}
                                    </p>
                                    <p className="text-[11px] text-white/40 group-hover:text-white/60 transition-colors duration-300">
                                      {item.description}
                                    </p>
                                  </div>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ))}
                  </div>
                </motion.div>
              </div>
            )}
          </AnimatePresence>
        </li>
      ))}
    </ul>
  );
}
