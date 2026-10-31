import { useRef } from "react";
import { Check } from "lucide-react";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { useCopyFlash } from "./copyFlash.js";
import { useI18n } from "@text-to-cad/ui/i18n";

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

// One line a row: the label at the left, as wide as its words, and the value at the
// right, taking the rest, so a short value never wraps under a wide empty label
// column. Sized for the tool stack's narrowest width: a value too long for what is
// left wraps between words, and breaks inside one only when the word alone is
// wider than its room (a long id). Compact (2px above and below), and in the
// panel's one face and size: labels and values alike are the UI font at
// `text-tiny`, numbers kept in tabular figures.
//
// The label carries what the row means (`title`), as a hint. A click on the value copies it, as
// it reads (`copy` says otherwise: a coordinate's `CoordValue` carries its own, "x, y, z"; a chip's ID
// row, its whole reference, made at the click where `copy` is a function), its
// pointer the only sign it can; for a moment "Copied" is drawn over it, the value kept in place unseen, so
// the row keeps its every line and baseline and nothing moves. `copy={false}` leaves a row
// uncopyable: one whose value is a link (a file, a parent link), which keeps its own click.
export function InfoRow({ label, children, title, copy }) {
  const { t } = useI18n();
  const value = useRef(null);
  const flash = useCopyFlash();
  const copyable = flash.canCopy && copy !== false;
  const onClick = () => {
    if (!copyable) return;
    const element = value.current;
    const text = typeof copy === "function" ? copy() : typeof copy === "string" ? copy
      : element?.querySelector("[data-copy]")?.getAttribute("data-copy") || element?.textContent || "";
    void flash.copy(text);
  };
  const copied = copyable && flash.copied;
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5" data-info-row="">
      <TooltipHint content={title}><span className="shrink-0 text-tiny text-muted-foreground">{label}</span></TooltipHint>
      <div onClick={onClick} data-copied={copied ? "" : undefined}
        className={cn("relative min-w-0 text-right text-tiny text-sidebar-foreground [overflow-wrap:break-word]",
          copyable && "cursor-pointer rounded-sm transition-colors hover:text-foreground")}>
        <div ref={value} className={copied ? "invisible" : undefined}>{children}</div>
        {copied ? <span className="absolute right-0 top-0 inline-flex items-center gap-1 whitespace-nowrap text-foreground">
          <Check className="size-2.5" aria-hidden="true"/>{t("chip.copied")}
        </span> : null}
      </div>
    </div>
  );
}

/** A number, an id or a colour: the UI font, with tabular figures so a column of them lines up. */
export function MonoValue({ children }) {
  return <span className="tabular-nums">{children}</span>;
}

export function CoordValue({ vector, digits = 2 }) {
  const values = Array.isArray(vector) ? vector : [];
  return (
    <span className="inline-flex flex-wrap items-baseline justify-end gap-x-3 gap-y-0.5 tabular-nums"
      data-copy={[0, 1, 2].map(index => +(Number(values[index]) || 0).toFixed(digits)).join(", ")}>
      {AXES.map((axis, index) => (
        <span key={axis.key} className="inline-flex items-baseline gap-1">
          <span className={axis.className}>{axis.key}</span>
          <span>{formatNumber(values[index], digits)}</span>
        </span>
      ))}
    </span>
  );
}
