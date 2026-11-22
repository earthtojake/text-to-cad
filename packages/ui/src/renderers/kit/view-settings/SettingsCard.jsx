import { Fragment } from "react";
import { X } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { FieldLabel } from "@cad/ui/primitives/field-label";
import { ValueDropdown } from "@cad/ui/primitives/value-dropdown";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { Switch } from "@cad/ui/primitives/switch";
import { cn } from "@cad/ui/utils";
import { hasOpenPopup } from "../../../lib/popups.js";
import { PANEL_PEEK_ELEVATION_CLASS, PANEL_PEEK_GAP_PX, PANEL_PEEK_IN_RIGHT_CLASS, PANEL_PEEK_OUT_RIGHT_CLASS, PANEL_PEEK_RADIUS_PX, useSlidingCard }
  from "../../../file-viewer/panelPeek.js";
import { FileSheetColorPicker } from "../inspector/FileSheet.js";
import { PANEL_ACTION_CLASS } from "../inspector/PanelActions.jsx";
import { SliderField } from "../inspector/SliderField.jsx";

/**
 * A settings card (`docs/design-system.md`, "The settings cards"): the view's **Display** card and Preview's **Settings**,
 * docked at the view's right edge, the sidebar's peek card's mirror. Its box is `SETTINGS_CARD_WIDTH_PX` wide on a
 * desktop (`--cad-card-min` on a phone), its surface the peek card's (its border, the
 * sidebar's colour, its shadow and radius), and it slides in from the right edge and back out as the peek does from the
 * left (`file-viewer/panelPeek.js`'s `PANEL_PEEK_IN_RIGHT_CLASS` and `PANEL_PEEK_OUT_RIGHT_CLASS`, the peek's durations and
 * easing). Its content stands as far inside its edge as the peek card's does: the panel's inset less the gap (12px), on
 * all four sides.
 *
 * Inside, the card is drawn from `sections`, each a list of rows, with ONE hairline between sections and none between
 * rows: 24px controls on a 32px pitch (8px apart), the rule 12px from what is seen on either side of it. A row is
 * `{ kind, id, ... }`:
 *
 * - `"select"`: `label`, `name` (its accessible name, where longer), `value`, `options` (`{ value, label, Icon?,
 *   disabled? }`), `onChange`, `data` (the attribute each option carries). Every dropdown of a card is ONE width: half
 *   the card's content, or as wide as the card's widest option where that is wider (the labels keep the rest, whole);
 *   each shows its value's icon, where the options have icons.
 * - `"switch"`: `label`, `value`, `onChange`, `controlProps` (attributes on the switch); `head`: the section's heading
 *   too (its label in the heading's ink).
 * - `"color"`: `label`, `name`, `value`, `onChange`, `disabled`: a colour, as wide as its value.
 * - `"slider"`: `label`, `name`, `value`, its range and increment (`min`, `max` and the increment's key), `scale`,
 *   `text`, `valueLabel`, `onCommit`, `onChange`: the slider control (`SliderField.jsx`, `compact`), its label and value
 *   on a 24px line, the track under it.
 * - `"heading"`: `label`, the section's name, in the foreground at medium weight.
 * - `"custom"`: `label` and `node`, a control of its own (a palette), its label in the label column.
 */

/**
 * The card's width on a desktop: wide enough that half its content (132px, inside its 12px inset) holds the longest
 * option of any card (a 3D file's "Orthographic", 123px, with room for a wider font), so every dropdown is half its row
 * as on a phone (`docs/design-system.md`, "Half the row"). A phone's is `--cad-card-min`.
 */
export const SETTINGS_CARD_WIDTH_PX = 288;
/** The card's gap to the view's edges, the peek card's. */
export const SETTINGS_CARD_GAP_PX = PANEL_PEEK_GAP_PX;
/**
 * The card's layer (`docs/design-system.md`, "Layering"): the view's top layer's (`ViewFrame.jsx`'s strip and Quick Edit),
 * drawn after it, so over the strip, the corner's cube or zoom and the picture; menus, tooltips and dialogs, portalled
 * to the page's end on the same layer, stand over it.
 */
export const SETTINGS_CARD_LAYER_CLASS = "z-50";
// Its content's inset from the card's outer edge: the peek card's (the panel's inset, less the gap), and so less its
// 1px border as padding. The title's 16px line stands 4px above the inset line, so its capitals' tops are on it; the X's
// 12px glyph ends on the inset line at the right and is centred on the title's capitals; Reset's 28px button hangs 8px
// past the line at the right (its padding) and stands so its text's baseline is on the line at the bottom.
const CARD_VARIABLES = Object.freeze({
  "--card-inset": `calc(var(--panel-inset) - ${PANEL_PEEK_GAP_PX}px)`,
  // At least the sidebar's width, and wider where its values need it (a phone's 14px ones), never past the view less
  // its gaps: nothing in it truncates.
  width: "max-content", minWidth: `var(--cad-card-min, ${SETTINGS_CARD_WIDTH_PX}px)`, maxWidth: "calc(100vw - 8px)", borderRadius: PANEL_PEEK_RADIUS_PX
});
const PAD = px => `calc(var(--card-inset) - ${px}px)`;
// The rows' grid: labels, then the controls' column, ONE width for the card's dropdowns: half the content, or the
// widest option where that is wider (the labels then keep the rest, whole).
const GRID_CLASS = "grid grid-cols-[minmax(max-content,1fr)_minmax(50%,max-content)] content-start items-center gap-x-2 gap-y-2";
// A row is its label and its control, each a cell of the card's grid (the row itself draws no box); its label's cell
// is 24px at least, so a row is as tall as its control where that is taller (a phone's 36px dropdown), never less.
const ROW_CLASS = "contents";
// A dropdown: today's panel dropdown at 24px, its padding and gap the design system's tightest (`Toggle`'s sm, the
// colour field's) and its chevron the panel dropdown's 12px (`panelRows.jsx`), so a card's widest value fits beside its
// widest label.
const TRIGGER_CLASS = "!h-icon-button w-full min-w-0 justify-self-stretch gap-1 px-1.5 py-2 text-xs";
// What a row's first and last visible edge are, below and above its box: a 14px switch is centred in its 24px row,
// a heading's capitals stand 4px into its 16px line. The rule keeps 12px from them on either side (8px is the gap).
const INK_TOP = Object.freeze({ switch: 5, heading: 4 });
const INK_BOTTOM = Object.freeze({ switch: 5 });
const RULE_AIR_PX = 12, ROW_GAP_PX = 8;

/**
 * The dock: the view's right edge, `SETTINGS_CARD_GAP_PX` from it and from the bottom (the top is the caller's:
 * under the navbar, or under Preview's bar), the card as tall as its content within it. `open` slides the card in;
 * closed, it slides back out and is gone.
 */
export function SettingsCardDock({ open, className = "", style = undefined, children, ...props }) {
  const slide = useSlidingCard(open);
  if (!slide.shown) return null;
  return <div className={cn("pointer-events-none absolute flex min-h-0 flex-col items-end", className)}
    style={{ right: SETTINGS_CARD_GAP_PX, bottom: SETTINGS_CARD_GAP_PX, ...style }} data-open={open ? "" : undefined} {...props}>
    <div className={cn("flex max-h-full min-h-0 max-w-full flex-col", slide.leaving ? PANEL_PEEK_OUT_RIGHT_CLASS : PANEL_PEEK_IN_RIGHT_CLASS)} inert={slide.leaving}
      data-settings-card-slide={slide.leaving ? "out" : "in"}
      onAnimationEnd={event => { if (slide.leaving && event.target === event.currentTarget) slide.exited(); }}>{children}</div>
  </div>;
}

function Choice({ row }) {
  // The one value dropdown, as wide as its widest option, so the card's dropdowns keep their width whatever is chosen.
  return <ValueDropdown value={row.value} options={row.options} onChange={row.onChange} label={row.name ?? row.label} fixedWidth
    iconClassName="size-3.5" className={TRIGGER_CLASS} triggerProps={{ "aria-label": row.name ?? row.label, "data-settings-select": row.id }}
    optionProps={row.data ? option => ({ [row.data]: option.value }) : null} />;
}

function Label({ row, head = false }) {
  return <span className="flex min-h-icon-button min-w-0 items-center">
    {head ? <span className="min-w-0 truncate text-xs leading-(--cad-leading-xs) font-medium text-foreground" data-settings-label="" data-settings-heading="">{row.label}</span>
      : <FieldLabel className="leading-(--cad-leading-xs)" data-settings-label="">{row.label}</FieldLabel>}
  </span>;
}

function Row({ row }) {
  const props = { "data-settings-row": row.id };
  if (row.kind === "heading") {
    return <h4 className="col-span-2 flex h-(--cad-leading-xs) min-w-0 items-center text-xs leading-(--cad-leading-xs) font-medium text-foreground" data-settings-heading="" {...props}>
      <span className="min-w-0 truncate">{row.label}</span>
    </h4>;
  }
  if (row.kind === "slider") {
    return <SliderField compact className="col-span-2" label={row.label} name={row.name ?? row.label} value={row.value} min={row.min} max={row.max}
      step={row.step} scale={row.scale ?? 1} text={row.text} onTextCommit={row.onCommit} textLabel={row.valueLabel} onValueChange={row.onChange} {...props} />;
  }
  if (row.kind === "switch") {
    return <label className={ROW_CLASS} {...props}>
      <Label row={row} head={row.head === true} />
      <Switch className="self-center justify-self-end" checked={row.value} aria-label={row.label} onCheckedChange={next => row.onChange(next === true)} {...row.controlProps} />
    </label>;
  }
  return <div className={ROW_CLASS} {...props}>
    <Label row={row} />
    {row.kind === "select" ? <Choice row={row} />
      : row.kind === "color" ? <FileSheetColorPicker aria-label={row.name ?? row.label} value={row.value} onChange={row.onChange} disabled={row.disabled === true}
        className="!h-icon-button w-fit self-center justify-self-end" />
      : <div className="self-center justify-self-end">{row.node}</div>}
  </div>;
}

// The rule between two sections: 12px from the last thing seen above it and from the first seen below it.
function Rule({ above, below }) {
  return <div aria-hidden="true" className="col-span-2 h-px bg-border" data-settings-rule=""
    style={{ marginTop: RULE_AIR_PX - ROW_GAP_PX - (INK_BOTTOM[above] ?? 0), marginBottom: RULE_AIR_PX - ROW_GAP_PX - (INK_TOP[below] ?? 0) }} />;
}
const inkKind = row => (row.kind === "switch" ? "switch" : row.kind === "heading" ? "heading" : "box");

/**
 * The card: its title and X at the top, its sections, and its Reset at the bottom right (the panel's own, as Params'
 * is: off while there is nothing to put back). Over a short view its sections scroll between the title and Reset,
 * which stay. `closeOnEscape`: Escape in it (a popup of its own first) is `onClose`'s, as the X is (Display's; Preview's
 * Escape is Preview's own, its way out).
 * @param {{ title: string, closeLabel: string, onClose(): void, sections: object[][], resetLabel?: string,
 *   onReset?: (() => void) | null, resetDisabled?: boolean, resetProps?: object, closeOnEscape?: boolean }} props  Other props go on the card.
 */
export function SettingsCard({ title, closeLabel, onClose, sections, resetLabel = "", onReset = null, resetDisabled = false, resetProps = null,
  closeOnEscape = false, ...props }) {
  const shown = sections.map(rows => rows.filter(Boolean)).filter(rows => rows.length);
  return <div role="region" aria-label={title} data-panel-surface="card" data-settings-card="" data-escape-owner={closeOnEscape ? "" : undefined} {...props}
    className={cn("pointer-events-auto relative flex max-h-full min-h-0 flex-col overflow-hidden border border-border bg-sidebar text-xs text-foreground", PANEL_PEEK_ELEVATION_CLASS)}
    style={CARD_VARIABLES}
    onKeyDown={event => {
      if (!closeOnEscape || event.key !== "Escape" || event.defaultPrevented || hasOpenPopup(event.currentTarget)) return;
      event.preventDefault();
      onClose();
    }}>
    {/* The title and its X on ONE line, at either scale: the X's button is centred on the title's line (its height
        hanging equally above and below it) and its 12px glyph ends on the inset line at the right. */}
    <div className="flex shrink-0 items-center gap-2" style={{ paddingTop: PAD(5), paddingLeft: PAD(1), paddingRight: PAD(1) }}
      data-settings-card-head="">
      <h3 className="min-w-0 flex-1 truncate text-xs leading-(--cad-leading-xs) font-medium text-foreground" data-settings-title="">{title}</h3>
      <button type="button" aria-label={closeLabel} onClick={onClose} data-settings-close=""
        className="flex size-icon-button shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45"
        style={{ marginBlock: "calc((var(--cad-leading-xs) - var(--cad-icon-button)) / 2)", marginRight: "calc((12px - var(--cad-icon-button)) / 2)" }}>
        <X className="size-3" aria-hidden="true" />
      </button>
    </div>
    <ScrollArea className="min-h-0 flex-1" viewportProps={{ "data-settings-card-scroller": "" }}>
      <div className={GRID_CLASS} style={{ paddingLeft: PAD(1), paddingRight: PAD(1), paddingTop: 12, paddingBottom: onReset ? 4 : PAD(1) }}
        data-settings-card-body="">
        {shown.map((rows, index) => <Fragment key={index}>
          {index ? <Rule above={inkKind(shown[index - 1].at(-1))} below={inkKind(rows[0])} /> : null}
          {rows.map(row => <Row key={row.id} row={row} />)}
        </Fragment>)}
      </div>
    </ScrollArea>
    {onReset ? <div className="flex shrink-0 justify-end" style={{ paddingRight: PAD(9), paddingBottom: 1 }} data-settings-card-foot="">
      <Button type="button" variant="ghost" size="xs" className={PANEL_ACTION_CLASS} disabled={resetDisabled} onClick={onReset} {...resetProps}>{resetLabel}</Button>
    </div> : null}
  </div>;
}
