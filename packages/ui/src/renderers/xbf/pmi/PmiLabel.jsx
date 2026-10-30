import { cn } from "@text-to-cad/ui/utils";
import { PmiGlyph } from "./pmiGlyphs.jsx";

// What a PMI callout says, drawn as a drawing draws it, at the UI's own size: a dimension's
// nominal (a diameter's struck circle before it) and its tolerance, stacked where it differs each
// way, a basic one's number boxed (it is exact: it has none), and one given its limits those alone,
// the upper over the lower, in place of a nominal; a datum's letter in its box; a feature control
// frame's cells -- its characteristic, its value (a diameter zone's struck circle first) and the
// datums it refers to -- each ruled off from the next; a flag note's flag and its number, its words
// the section's to read (its Notes). Ink on paper, so it reads over any part: the theme's
// foreground on its background.

const BOX = "inline-flex items-stretch rounded-[2px] border bg-background/95 text-tiny leading-4 tabular-nums text-foreground shadow-sm";
// A callout whose reference broke is in its status's colour, the theme's: one that names nothing or
// a face it cannot stand on in the destructive token, one that names several in amber. Its box's
// border here, and its leader the overlay reads from the same token (`PMI_STATUS_TOKENS`,
// `PmiOverlay.jsx`), so the two are one colour.
export const PMI_STATUS_TOKENS = Object.freeze({ missing: "--destructive", invalid: "--destructive", ambiguous: "--color-amber-500" });
const STATUS_BORDER = Object.freeze({ missing: "border-destructive", invalid: "border-destructive", ambiguous: "border-amber-500" });
const CELL = "flex items-center px-1";
const GLYPH = "size-3 shrink-0";

// Two deviations stacked, the upper over the lower, beside the nominal; limits stacked in its place.
function Tolerance({ tolerance }) {
  if (!tolerance) return null;
  if (tolerance.symmetric) return <span className="pl-0.5">{tolerance.text}</span>;
  return <span className={cn("inline-flex flex-col justify-center text-micro leading-[0.7rem]", !tolerance.limits && "ml-0.5")}
    data-pmi-tolerance="limits" data-pmi-limits={tolerance.limits ? "" : undefined}>
    <span>{tolerance.upper}</span><span>{tolerance.lower}</span>
  </span>;
}

/** A callout's words in their box: `pmiCallout`'s pieces, the box in its state's colour. */
export default function PmiLabel({ callout, status = "ok", selected = false, hovered = false, moved = false, className }) {
  // Picked or moved, in the selection blue the overlay draws its leaders in (`--pmi-selected`, `PmiOverlay.jsx`).
  const border = STATUS_BORDER[status] ? cn(STATUS_BORDER[status], "border-dashed")
    : selected ? "border-(--pmi-selected) ring-2 ring-(--pmi-selected)/35" : hovered ? "border-foreground" : "border-foreground/60";
  const box = cn(BOX, border, moved && "outline-dashed outline-1 outline-offset-2 outline-(--pmi-selected)", className);
  if (callout.kind === "dimension") {
    return <span className={cn(box, CELL, "gap-px py-px")} data-pmi-callout="dimension">
      {callout.diameter ? <PmiGlyph name="diameter" className={GLYPH} aria-hidden="true" /> : null}
      {callout.basic ? <span className="border border-current px-0.5 leading-[0.875rem]" data-pmi-basic="">{callout.nominal}</span>
        : callout.nominal === null ? null : <span>{callout.nominal}</span>}
      <Tolerance tolerance={callout.tolerance} />
    </span>;
  }
  if (callout.kind === "datum") {
    return <span className={cn(box, CELL, "min-w-5 justify-center py-px font-medium")} data-pmi-callout="datum">{callout.letter}</span>;
  }
  if (callout.kind === "frame") {
    return <span className={cn(box, "divide-x divide-current/40")} data-pmi-callout="frame">
      <span className={CELL}><PmiGlyph name={callout.characteristic} className={GLYPH} aria-hidden="true" /></span>
      <span className={cn(CELL, "gap-px")}>
        {callout.diameter ? <PmiGlyph name="diameter" className={GLYPH} aria-hidden="true" /> : null}
        {callout.value}
      </span>
      {callout.datums.map(datum => <span key={datum} className={CELL}>{datum}</span>)}
    </span>;
  }
  if (callout.kind === "note") {
    return <span className={cn(box, CELL, "gap-0.5 py-px font-medium")} data-pmi-callout="note">
      <PmiGlyph name="flag" className={GLYPH} aria-hidden="true" />{callout.number}
    </span>;
  }
  return <span className={cn(box, CELL, "gap-1 py-px text-muted-foreground")} data-pmi-callout="unsupported">
    <PmiGlyph name="unsupported" className={GLYPH} aria-hidden="true" />{callout.text}
  </span>;
}
