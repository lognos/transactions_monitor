import { cn } from "@/lib/cn";

// The app's only logo: the "TSX" badge.
export function TsxMark({ size = "sm", className }: { size?: "sm" | "lg"; className?: string }) {
  return (
    <span
      aria-label="TSX"
      role="img"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg border border-status-info-border bg-accent-subtle font-mono font-semibold text-accent-fg",
        size === "sm" ? "size-9 text-[11px] tracking-wide" : "h-14 px-5 text-2xl tracking-[0.18em]",
        className,
      )}
    >
      TSX
    </span>
  );
}

// Four-square mark used on the sign-in buttons.
export function MicrosoftLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 23 23" aria-hidden="true">
      <path fill="#f35325" d="M1 1h10v10H1z" />
      <path fill="#81bc06" d="M12 1h10v10H12z" />
      <path fill="#05a6f0" d="M1 12h10v10H1z" />
      <path fill="#ffba08" d="M12 12h10v10H12z" />
    </svg>
  );
}
