import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "info" | "positive" | "attention" | "negative";
export type BadgeSize = "sm" | "md";

// Full literal class strings: Tailwind only sees classes written out in source.
const TONES: Record<BadgeTone, string> = {
  neutral: "bg-status-neutral-bg text-status-neutral-fg border-status-neutral-border",
  info: "bg-status-info-bg text-status-info-fg border-status-info-border",
  positive: "bg-status-positive-bg text-status-positive-fg border-status-positive-border",
  attention: "bg-status-attention-bg text-status-attention-fg border-status-attention-border",
  negative: "bg-status-negative-bg text-status-negative-fg border-status-negative-border",
};

const SIZES: Record<BadgeSize, string> = {
  sm: "px-1.5 py-0.5 text-2xs",
  md: "px-2 py-0.5 text-xs",
};

export interface BadgeProps {
  tone?: BadgeTone;
  size?: BadgeSize;
  icon?: LucideIcon;
  className?: string;
  title?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", size = "md", icon: Icon, className, title, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border font-medium whitespace-nowrap",
        TONES[tone],
        SIZES[size],
        className,
      )}
    >
      {Icon && <Icon className="size-3" aria-hidden="true" />}
      {children}
    </span>
  );
}
