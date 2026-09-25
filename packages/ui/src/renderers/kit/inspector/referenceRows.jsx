import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { cn } from "@hardcore/ui/utils";

// Onshape-style axis colour coding for coordinate triples.
const AXES = Object.freeze([
  { key: "X", className: "text-rose-500 dark:text-rose-400" },
  { key: "Y", className: "text-emerald-500 dark:text-emerald-400" },
  { key: "Z", className: "text-sky-500 dark:text-sky-400" }
]);

export function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

// Label-column rows keep the value next to its label instead of pushing it to
// the far edge, so the readout scans top-to-bottom.
export function InfoRow({ label, children, title }) {
  return (
    <TooltipHint content={title}><div className="grid grid-cols-[5rem_minmax(0,1fr)] items-baseline gap-2 py-1" >
      <span className="text-tiny text-muted-foreground">{label}</span>
      <div className="min-w-0 flex-1 text-tiny text-sidebar-foreground [overflow-wrap:anywhere]">{children}</div>
    </div></TooltipHint>
  );
}

export function MonoValue({ children }) {
  return <span className="font-mono tabular-nums">{children}</span>;
}

export function CoordValue({ vector, digits = 2 }) {
  const values = Array.isArray(vector) ? vector : [];
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono tabular-nums">
      {AXES.map((axis, index) => (
        <span key={axis.key} className="inline-flex items-baseline gap-1">
          <span className={cn("text-micro", axis.className)}>{axis.key}</span>
          <span>{formatNumber(values[index], digits)}</span>
        </span>
      ))}
    </span>
  );
}
