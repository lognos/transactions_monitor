"use client";

import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function Select({ className, ...rest }: SelectProps) {
  return (
    <select
      className={cn(
        "h-(--control-h-md) rounded-md border border-border-default bg-surface-1 px-2.5 text-sm font-light text-text-default",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus",
        className,
      )}
      {...rest}
    />
  );
}
