import * as React from "react";
import { cn } from "@cad/ui/utils";

// THE segmented control (`docs/design-system.md`, "Pills and the segmented control"): one choice of two (or a few)
// ways to show the same thing, its options side by side on one muted track and the chosen one raised on it. Each option
// is a toggle (`aria-pressed`) in a labelled group, the control tall (28; a phone's 36) so a finger's press is the
// scale's, its face drawn 2px in from its edges: the track shows 2px round the faces and 4px between them, and the
// track's corners are a face's + 2, so the curves run parallel. The group is one Tab stop, on the chosen option; ← and →
// (and Home and End) choose the neighbour and wrap, as a tab list's keys do.

const TRACK_CLASS = "inline-flex shrink-0 items-center rounded-[calc(var(--cad-radius-control)+2px)] bg-muted";
// An icon option is the control + 4 wide (its face 28 by 24; a phone's 36 by 32); a worded one as wide as its word.
const OPTION_CLASS = "group/segment grid h-control shrink-0 place-items-stretch p-0.5 outline-none";
const FACE_CLASS = "grid place-items-center rounded-control text-muted-foreground transition-colors [&_svg]:size-glyph [&_svg]:shrink-0 "
  + "group-hover/segment:text-foreground group-focus-visible/segment:ring-2 group-focus-visible/segment:ring-ring/45";
const ON_CLASS = "bg-background text-foreground shadow-xs dark:bg-accent";

/**
 * @typedef {{ value: string, label: string, Icon?: import("react").ComponentType<any> | null }} SegmentOption
 * @param {{ value: string, options: readonly SegmentOption[], onChange(value: string): void, label: string, className?: string }} props
 *   `label`: the group's accessible name; an option with an `Icon` shows it alone, named by its `label`.
 */
export function SegmentedControl({ value, options, onChange, label, className }) {
  const buttons = React.useRef([]);
  const chosen = Math.max(0, options.findIndex(option => option.value === value));
  const choose = index => { const option = options[index]; if (option.value !== value) onChange(option.value); };
  return <div role="group" aria-label={label} className={cn(TRACK_CLASS, className)} data-segmented-control="">
    {options.map((option, index) => {
      const on = option.value === value;
      return <button key={option.value} ref={node => { buttons.current[index] = node; }} type="button" aria-pressed={on}
        aria-label={option.Icon ? option.label : undefined} tabIndex={index === chosen ? 0 : -1} data-segment={option.value}
        className={cn(OPTION_CLASS, option.Icon ? "w-[calc(var(--cad-control)+4px)]" : "text-ui")}
        onClick={() => choose(index)}
        onKeyDown={event => {
          const count = options.length;
          const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: count - 1 }[event.key];
          if (next === undefined) return;
          event.preventDefault();
          const to = (next + count) % count;
          choose(to);
          buttons.current[to]?.focus();
        }}>
        <span className={cn(FACE_CLASS, !option.Icon && "px-1.5", on && ON_CLASS)}>{option.Icon ? <option.Icon aria-hidden="true" /> : option.label}</span>
      </button>;
    })}
  </div>;
}
