"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

// Native modal dialogs make everything underneath inert, including another
// dialog. This stack also limits keyboard handling to the current top layer.
const modalStack: HTMLDialogElement[] = [];

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, description, children, className }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog) return;

    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    modalStack.push(dialog);

    return () => {
      const index = modalStack.indexOf(dialog);
      if (index !== -1) modalStack.splice(index, 1);
      dialog.close();
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className={cn(
        "m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-5xl overflow-y-auto rounded-xl border border-border-default bg-surface-1 p-0 text-text-default shadow-2xl backdrop:bg-surface-base/80 backdrop:backdrop-blur-sm",
        className,
      )}
      onCancel={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (modalStack.at(-1) === dialogRef.current) onClose();
      }}
      onKeyDown={(event) => {
        const dialog = dialogRef.current;
        if (!dialog || modalStack.at(-1) !== dialog) return;
        if (event.key === "Escape") event.stopPropagation();
        if (event.key !== "Tab") return;

        const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]',
        )).filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0);
        const first = focusable[0];
        const last = focusable.at(-1);
        if (!first || !last) {
          event.preventDefault();
          return;
        }
        if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border-subtle bg-surface-1 px-6 py-4">
        <div>
          <h2 id={titleId} className="text-xl font-semibold">{title}</h2>
          {description && <p id={descriptionId} className="mt-1 text-sm text-text-muted">{description}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="rounded-md p-2 text-text-muted hover:bg-surface-3 hover:text-text-default focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      </header>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
