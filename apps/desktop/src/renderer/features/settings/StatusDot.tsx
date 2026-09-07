/**
 * The one-glyph answer to "is this thing there": a coloured dot and a word.
 *
 * Shared by the Agents drawer and About's runtime block so "found", "missing"
 * and "working on it" look the same in both, and so the colour is decided once
 * rather than per call site.
 */
import { cn } from "cn";

export type Tone = "ok" | "warn" | "bad" | "idle" | "busy";

const TONES: Record<Tone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-destructive",
  idle: "bg-muted-foreground/50",
  busy: "bg-sky-500 animate-pulse",
};

export function StatusDot({ tone, className }: { tone: Tone; className?: string }) {
  return <span className={cn("size-2 shrink-0 rounded-full", TONES[tone], className)} />;
}

/** A dot with its label, for use as a row's control. */
export function StatusLabel({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)}>
      <StatusDot tone={tone} />
      <span className="truncate" data-selectable>
        {children}
      </span>
    </span>
  );
}
