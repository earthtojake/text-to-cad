import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@renderer/lib/utils";

/**
 * The one empty state, used by every tab kind.
 *
 * An empty pane is the surface a person sees most often on a first run, so it
 * is designed rather than blank: a framed glyph, a sentence that says what the
 * pane is for, and the action that fills it. Having one component for all four
 * is what keeps them looking like the same app.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  tone = "muted",
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  /** `warn` is for a state that is a missing prerequisite, not an idle one. */
  tone?: "muted" | "warn";
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col items-center justify-center gap-3 px-8 text-center",
        className,
      )}
    >
      <div
        className={cn(
          "flex size-11 items-center justify-center rounded-xl border",
          tone === "warn"
            ? "border-amber-500/25 bg-amber-500/10 text-amber-600 dark:text-amber-400"
            : "bg-muted/40 text-muted-foreground",
        )}
      >
        <Icon className="size-5" strokeWidth={1.5} />
      </div>
      <div className="space-y-1">
        <p className="text-[13px] font-medium">{title}</p>
        {description ? (
          <p className="max-w-[320px] text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
