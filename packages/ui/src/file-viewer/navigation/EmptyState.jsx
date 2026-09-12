import { cn } from "@hardcore/ui/utils";

/**
 * The one empty state, used by every pane in both apps.
 *
 * An empty pane is the surface a person sees most often on a first run, so it
 * is designed rather than blank: a framed glyph, a sentence that says what the
 * pane is for, and the action that fills it. Having one component for all of
 * them is what keeps them looking like the same app — the desktop's file tab
 * with nothing open and the standalone viewer at a bare origin are the SAME
 * empty pane, not two that resemble each other.
 *
 * @param {object} props
 * @param {import("react").ElementType} props.icon A lucide glyph.
 * @param {string} props.title
 * @param {string} [props.description]
 * @param {import("react").ReactNode} [props.action]
 * @param {string} [props.className]
 * @param {"muted"|"warn"} [props.tone]
 *   `warn` is for a state that is a missing prerequisite, not an idle one.
 */
export function EmptyState({ icon: Icon, title, description, action, className, tone = "muted" }) {
  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col items-center justify-center gap-3 px-8 text-center",
        className
      )}
    >
      <div
        className={cn(
          "flex size-11 items-center justify-center rounded-xl border",
          tone === "warn"
            ? "border-amber-500/25 bg-amber-500/10 text-amber-600 dark:text-amber-400"
            : "bg-muted/40 text-muted-foreground"
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
