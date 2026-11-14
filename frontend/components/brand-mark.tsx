import { cn } from "@/lib/cn";

// Two-approver mark from the supplied AuditFlow AI concept 03.
// Brand text beside the mark supplies its accessible name.
export function AuditFlowMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 96 96"
      aria-hidden="true"
      className={cn("size-9 shrink-0 text-text-default", className)}
      fill="currentColor"
    >
      <circle cx="33" cy="48" r="30" fill="none" stroke="currentColor" strokeWidth="5" />
      <circle cx="63" cy="48" r="30" fill="none" stroke="currentColor" strokeWidth="5" />
      <path d="M48 22.02a30 30 0 0 1 0 51.96 30 30 0 0 1 0-51.96Z" />
    </svg>
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
