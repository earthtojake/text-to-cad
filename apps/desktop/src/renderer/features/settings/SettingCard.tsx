import { cn } from "cn";

/**
 * The card-grouped row: title and one-line description on the left, the
 * control on the right (plan §2, Codex settings).
 *
 * Every settings page is built from these two components and nothing else, so
 * the pages stay declarative and a new one cannot invent its own row spacing.
 */
export function SettingCard({
  title,
  children,
  className,
}: {
  /** Optional plain heading above the card. */
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("mb-6", className)}>
      {title ? (
        <h2 className="mb-2 px-1 text-[13px] font-medium text-muted-foreground">{title}</h2>
      ) : null}
      <div className="divide-y overflow-hidden rounded-xl border bg-card">{children}</div>
    </section>
  );
}

export function SettingRow({
  title,
  description,
  control,
}: {
  title: string;
  description?: string;
  /** Toggle, select, segmented control, field or button. */
  control?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm">{title}</p>
        {description ? (
          <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{description}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">{control}</div>
    </div>
  );
}

/** A row whose control is not ready yet, marked with the phase that owns it. */
export function PendingRow({
  title,
  description,
  phase,
}: {
  title: string;
  description?: string;
  phase: string;
}) {
  return (
    <SettingRow
      control={
        <span className="rounded-full border border-dashed px-2 py-0.5 text-[11px] text-muted-foreground">
          {phase}
        </span>
      }
      description={description}
      title={title}
    />
  );
}
