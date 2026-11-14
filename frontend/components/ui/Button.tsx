"use client";

import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "ghost" | "action-sm" | "danger";

const BASE =
  "inline-flex items-center justify-center gap-2 font-light transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus";

const QUIET =
  "bg-surface-2/50 hover:bg-surface-3 text-text-muted hover:text-text-default border border-border-subtle hover:border-border-default";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "px-4 h-(--control-h-md) text-sm rounded-md bg-accent hover:bg-accent-hover text-text-on-accent",
  ghost: `px-4 h-(--control-h-md) text-sm rounded-md ${QUIET}`,
  "action-sm": `px-3 h-(--control-h-sm) text-xs rounded ${QUIET}`,
  danger:
    "px-4 h-(--control-h-md) text-sm rounded-md border border-status-negative-border bg-status-negative-bg text-status-negative-fg hover:opacity-80",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export function Button({ variant = "primary", className, type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={cn(BASE, VARIANTS[variant], className)} {...rest} />;
}
