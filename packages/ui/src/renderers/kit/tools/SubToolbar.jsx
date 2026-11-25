import { createContext, useContext, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { useStripTouch } from "./stripTouch.js";

// Whether the row in hand wrapped onto more than one line (a phone's): its rules then go.
const Wrapped = createContext(false);

/**
 * How many lines a wrapping row's children stand on: the distinct tops among the ones that are
 * drawn (a second line starts lower than the first).
 * @param {{ children: ArrayLike<{ offsetTop: number, offsetWidth: number, offsetHeight: number }> }} element
 */
export function rowsOf(element) {
  const tops = new Set();
  for (const child of Array.from(element?.children || [])) {
    if (child.offsetWidth || child.offsetHeight) tops.add(Math.round(child.offsetTop));
  }
  return tops.size;
}

// On a phone a row's buttons are the strip's 36px tiles, their icons 18px, and its slider is as tall,
// its thumb big enough to take with a finger.
// A chip in the row (Measure's measurements, `ReferenceChips.jsx`) keeps its own size.
// The strip's own proportions (`stripTouch.js`'s `TOP_STRIP_*`, Figma's toolbar's), at THE scale (`globals.css`): a row
// the control and 12px tall with its border, its corners the control's and 6, 5px in, its buttons the control with the
// control's corners and the glyph for icons (a word button keeps its width, at the row's height); a phone's the same
// class at a phone's tokens. A chip keeps its own size here too.
const ROW_CLASS = [
  "min-h-[calc(var(--cad-control)+12px)] rounded-[calc(var(--cad-radius-control)+6px)] p-[5px]",
  "[&_button:not([data-quick-edit-refs]_*)]:h-control [&_button:not([data-quick-edit-refs]_*)]:min-w-control [&_button:not([data-quick-edit-refs]_*)]:rounded-control [&_button:not([data-quick-edit-refs]_*)_svg]:size-glyph!"
].join(" ");

/**
 * A tool's own controls while it is in hand: one row hung under the strip, on the strip's surface,
 * at the strip's proportions (a 40px row, 28px buttons, 16px icons; a phone's 48px row of 36px tiles, its scale), its groups — what the tool does, how
 * it looks, what it can undo — parted by a thin rule (`SubToolbarSeparator`), as a design tool's
 * options bar is. It stays up for as long as its tool does. On a phone a row wider than the view
 * wraps (Shapes' at 375px), its groups then one under another: the rule between them, drawn for
 * groups side by side, would dangle at the first line's end, so a wrapped row draws none
 * (`data-wrapped`, measured from its children's tops on each resize; the rule keeps its room, so
 * hiding it never re-flows the row).
 *
 * @param {{ label: string, className?: string, children: import("react").ReactNode }} props
 *   `label` names the row for assistive technology ("Drawing controls").
 */
export default function SubToolbar({ label, className, children, ...props }) {
  const touch = useStripTouch();
  const root = useRef(null);
  const [wrapped, setWrapped] = useState(false);
  // Measured after every render (a tool's row changes with its tool) and on each resize of the row.
  useLayoutEffect(() => {
    if (!touch) { setWrapped(false); return; }
    if (root.current) setWrapped(rowsOf(root.current) > 1);
  });
  useLayoutEffect(() => {
    const element = root.current;
    if (!touch || !element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => setWrapped(rowsOf(element) > 1));
    observer.observe(element);
    return () => observer.disconnect();
  }, [touch]);
  return <Wrapped.Provider value={touch && wrapped}>
    <div ref={root} role="toolbar" aria-label={label} data-cad-sub-toolbar="" data-touch={touch ? "" : undefined} data-wrapped={touch && wrapped ? "" : undefined} {...props}
      className={cn("pointer-events-auto inline-flex max-w-full flex-wrap items-center gap-1", FLOATING_CHROME_SURFACE_CLASS,
        ROW_CLASS, className)}>
      {children}
    </div>
  </Wrapped.Provider>;
}

// The tools' sub-toolbars are one width on a desktop, 240px: the drawing tools' (its first row's seven 28px buttons) and
// the model effects' (a slider and its buttons), so the column under the strip does not change width
// from one tool to the next.
export const SUB_TOOLBAR_WIDTH_CLASS = "w-[240px]";

/**
 * The width of a slider tool's sub-toolbar: one width for all of them, its slider control
 * (`inspector/SliderField.jsx`, `inline`) taking whatever its buttons leave, so a conditional button
 * shortens the slider rather than the row.
 */
export const SLIDER_SUB_TOOLBAR_CLASS = `${SUB_TOOLBAR_WIDTH_CLASS} flex-nowrap data-[touch]:w-80`;

/** The thin rule between a sub-toolbar's groups; invisible, its room kept, where the row wrapped. */
export function SubToolbarSeparator() {
  const wrapped = useContext(Wrapped);
  return <span role="separator" aria-orientation="vertical" className={cn("mx-0.5 h-4 w-px shrink-0 bg-border", wrapped && "invisible")}
    data-sub-toolbar-rule="" data-hidden={wrapped ? "" : undefined} />;
}
