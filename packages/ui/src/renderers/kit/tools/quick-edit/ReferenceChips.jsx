import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Check, Copy, X } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { useViewerMobile } from "../../../../file-viewer/responsive.js";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { useCopyFlash } from "../../inspector/copyFlash.js";
import { InfoRow } from "../../inspector/referenceRows.jsx";
import { PickGlyph, compactSuffix, hasPickGlyph } from "../../inspector/pickGlyph.jsx";
import { useI18n } from "@text-to-cad/ui/i18n";

/**
 * One chip: what a renderer says a piece of its selection is. Several picks of one kind on one part
 * are ONE chip ("base · 6 faces"), so a grouped pick or a long run of picks never floods the box.
 * @typedef {object} ReferenceChip
 * @property {string} key  Stable while the chip stands for the same picks.
 * @property {string} label  Its words: "base · face 3", "base · 6 faces", "upper_arm". Its accessible
 *   name always, and what it shows unless it has a `compact` one.
 * @property {import("../../inspector/pickGlyph.jsx").CompactName} [compact]  What it shows, short:
 *   its part, then its kind's glyph and its number or count ("base ◧3", "base ◧×6"); with no part name
 *   (a document of one part, which the page already names), its `words` after the glyph ("◧face 1").
 * @property {string} [id]  Its id in its file, as its card shows it: "f:base.make_box1.3", "upper_arm".
 * @property {string | (() => string)} [copy]  What a click on it copies: its reference, the file's path and its
 *   id; or a reference resolved at the click. Annotation and measurement chips omit this.
 * @property {import("react").ReactNode} [card]  What it is, for its card: its key measurements.
 * @property {import("react").ReactNode} [icon]  Before its words: a measurement's ruler in its colour, the annotation's pen.
 * @property {string} [glyph]  Else, the glyph of what it names (`pickGlyph.jsx`: "solid" for a part, "face", "edge",
 *   "vertex", "ruler" for a measurement, "pencil" for the annotation); a compact name's own kind where it has none.
 * @property {string} [glyphColor]  The glyph's colour, where it has its own (a measurement's); else muted.
 * @property {string} [text]  The words beside an icon, where they are shorter than its accessible `label`.
 * @property {() => void} [onRemove]  Drops these picks from the selection.
 * @property {(on: boolean) => void} [onHover]  Lights these picks in the view while the pointer is on the chip.
 */

// A part's name on a chip is cut to this many characters, an ellipsis last: the chip's card (or, with
// none, its hint) gives the whole name.
export const CHIP_NAME_CHARS = 16;
// A card's ID row is one line of this many characters at most, its middle cut: the whole reference is
// its hint, and what a click on it copies.
export const CARD_ID_CHARS = 28;
export const capName = (name, chars = CHIP_NAME_CHARS) => (name.length > chars ? `${name.slice(0, chars - 1).trimEnd()}…` : name);
export function elideMiddle(text, chars = CARD_ID_CHARS) {
  if (text.length <= chars) return text;
  const head = Math.ceil((chars - 1) / 2), tail = Math.floor((chars - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - tail)}`;
}

// The chips the box shows before the rest go under "+N more": one or two lines at the box's width.
export const VISIBLE_REFERENCE_CHIPS = 4;
// A card opens to the left of what it is the card of, over the view rather than over the chips
// under it. It follows the pointer onto a chip after a moment, and stays while the pointer is on
// it or its card. A click copies the chip's reference; a press with no pointer to rest (a touch,
// a key) opens the card too. A card is as tall as its rows, up to the room the view has.
const OPEN_DELAY_MS = 300;
const CLOSE_DELAY_MS = 150;
const CHIP_CLASS = "inline-flex h-5 min-w-0 max-w-full items-center rounded-sm bg-accent/70 text-tiny text-foreground";
const CHIP_LABEL_CLASS = "min-w-0 truncate rounded-sm px-1.5 leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
const CHIP_REMOVE_CLASS = "-ml-0.5 mr-0.5 flex size-4 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
const POPOVER_CLASS = cn(FLOATING_SURFACE_CLASS, "p-0 text-tiny data-[state=closed]:animate-none!");
// What the room left by a card's title and padding is: the rest of the view's height is its rows'.
const CARD_ROWS_STYLE = { maxHeight: "calc(var(--radix-popover-content-available-height, 32rem) - 2.25rem)" };
const LIST_STYLE = { maxHeight: "calc(var(--radix-popover-content-available-height, 32rem) - 0.5rem)" };

function useHoverOpen(card) {
  const [open, setOpen] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  const settle = (next, delay) => { clearTimeout(timer.current); timer.current = setTimeout(() => setOpen(next), delay); };
  return {
    open: open && card, setOpen,
    // A mouse only: a touch opens the card by its press.
    enter: event => { if (event.pointerType === "mouse" && card) settle(true, OPEN_DELAY_MS); },
    stay: event => { if (event.pointerType === "mouse") clearTimeout(timer.current); },
    leave: event => { if (event.pointerType === "mouse") settle(false, CLOSE_DELAY_MS); },
  };
}

/**
 * A chip's behaviour wherever it is drawn (in the box, or a row of "+N more"): its card on a rest of
 * the pointer, its picks lit meanwhile, its reference copied by a click — "Copied" in its label's
 * place, held at the label's width so nothing shifts — and the card opened by a touch's press.
 */
// What a chip shows: its compact name where it has one (its part, then a glyph and a number), else its words.
// Every chip leads with its icon (`icon`, else the glyph of what it names), then its words: its compact
// name's part and its number or count where it has one, else its own.
// A part's name is cut to `CHIP_NAME_CHARS` (a compact name's part, a whole part's chip); the number
// after it is never cut. A chip with a card shows the whole name in its card's title; one with none,
// in a hint.
function PartName({ name, hinted }) {
  const shown = capName(name);
  const text = <span className="min-w-0 truncate" data-chip-name="">{shown}</span>;
  return hinted && shown !== name ? <TooltipHint content={name}>{text}</TooltipHint> : text;
}

function ChipText({ chip }) {
  const { compact } = chip;
  const glyph = chip.glyph ?? compact?.kind;
  const icon = chip.icon ?? (hasPickGlyph(glyph)
    ? <PickGlyph kind={glyph} color={chip.glyphColor} className={cn("size-2.5 shrink-0", !chip.glyphColor && "text-muted-foreground")} /> : null);
  const named = compact && hasPickGlyph(compact.kind);
  const hinted = !(chip.card || chip.id);
  const words = chip.text ?? chip.label;
  return <span className="inline-flex min-w-0 max-w-full items-center gap-1 align-top" data-chip-compact={named ? "" : undefined}>
    {icon}
    {named ? compact.name ? <>
      <PartName name={compact.name} hinted={hinted} />
      <span className="shrink-0 text-muted-foreground">{compactSuffix(compact)}</span>
    </> : <span className="min-w-0 truncate">{compact.words ?? words}</span>
      : glyph === "solid" ? <PartName name={words} hinted={hinted} /> : <span className="min-w-0 truncate">{words}</span>}
  </span>;
}

// What a click copies: the chip's reference, or what it makes then (`copy` a function).
const copyChip = (flash, chip) => flash.copy(typeof chip.copy === "function" ? chip.copy() : chip.copy);

function useChip(chip) {
  const { t } = useI18n();
  const card = Boolean(chip.card || chip.id);
  const hover = useHoverOpen(card);
  const flash = useCopyFlash();
  const label = useRef(null);
  const anchor = useRef(null);
  const pointer = useRef("");
  const [width, setWidth] = useState(0);
  const copyable = Boolean(chip.copy) && flash.canCopy;
  const copied = copyable && flash.copied;
  // On a phone a tap is for reading: it opens the card, whose title copies.
  const tapCopies = !useViewerMobile();
  return {
    card, hover, copyable, copied,
    // A press on the chip is not one outside its card: the card stays while the chip copies.
    keepOnChip: event => { if (anchor.current?.contains(event.target)) event.preventDefault(); },
    surface: {
      ref: anchor,
      "data-quick-edit-ref": chip.key,
      onPointerEnter: event => { if (event.pointerType === "mouse") chip.onHover?.(true); hover.enter(event); },
      onPointerLeave: event => { if (event.pointerType === "mouse") chip.onHover?.(false); hover.leave(event); },
    },
    label: {
      ref: label, type: "button", "aria-label": chip.label, "data-copied": copied ? "" : undefined,
      style: copied && width ? { minWidth: width } : undefined,
      onPointerDown: event => { pointer.current = event.pointerType; },
      onClick: () => {
        if (copyable && tapCopies) { setWidth(label.current?.offsetWidth || 0); void copyChip(flash, chip); }
        if (pointer.current !== "mouse" && card) hover.setOpen(open => !open);
        pointer.current = "";
      },
      children: copied ? <span className="inline-flex items-center gap-1"><Check className="size-2.5" aria-hidden="true" />{t("chip.copied")}</span> : <ChipText chip={chip} />,
    },
  };
}

function RemoveButton({ chip }) {
  const { t } = useI18n();
  return chip.onRemove ? <button type="button" className={CHIP_REMOVE_CLASS} aria-label={t("chip.remove", { name: chip.label })}
    onClick={() => { chip.onHover?.(false); chip.onRemove(); }}><X className="size-2.5" aria-hidden="true" /></button> : null;
}

// A card's title: the chip's name with a small copy icon after it, the two a button that copies
// what the chip does (no hint: the icon says it), the icon a tick for a moment once it has.
function CardTitle({ chip }) {
  const flash = useCopyFlash();
  const { t } = useI18n();
  if (!chip.copy || !flash.canCopy) return <p className="truncate px-2 pt-1.5 text-tiny text-foreground">{chip.label}</p>;
  const Icon = flash.copied ? Check : Copy;
  // Only the name and its icon are the button, tight together; the rest of the row is not.
  return <div className="flex min-w-0 px-2 pt-1.5">
    <button type="button" aria-label={t("chip.copyReference", { name: chip.label })} data-copied={flash.copied ? "" : undefined}
      onClick={() => void copyChip(flash, chip)}
      className="group/title inline-flex min-w-0 max-w-full cursor-pointer items-center gap-1 rounded-sm text-left text-tiny text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/45">
      <span className="min-w-0 truncate">{chip.label}</span>
      <Icon className={cn("size-2.5 shrink-0", flash.copied ? "text-foreground" : "text-muted-foreground group-hover/title:text-foreground")} aria-hidden="true" />
    </button>
  </div>;
}

// A chip's card: its name, its id, then what the renderer says of it (or its picture).
// Beside the box, a card opens to its left, over the view; on a phone the box is the bottom sheet
// across the screen, so the card opens above the chip, inside the screen.
// Where the chips hang: "below", under the strip (Measure's row), opens every card under its chip.
const ChipsBelowContext = createContext(false);

function useCardPlace() {
  const mobile = useViewerMobile();
  if (useContext(ChipsBelowContext)) return { side: "bottom", align: "start", sideOffset: 6 };
  return mobile ? { side: "top", align: "start", sideOffset: 6 } : { side: "left", align: "start", sideOffset: 14 };
}

// A card's ID: one monospace line, its middle cut where it is long (`elideMiddle`), the whole of it
// its hint; a click copies the chip's whole reference, what its title copies.
function IdRow({ chip }) {
  const { t } = useI18n();
  const shown = elideMiddle(chip.id);
  const value = <span className="inline-block max-w-full whitespace-nowrap align-top font-mono" data-chip-id="">{shown}</span>;
  return <InfoRow label={t("chip.id")} copy={() => (typeof chip.copy === "function" ? chip.copy() : chip.copy || chip.id)}>
    {shown === chip.id ? value : <TooltipHint content={chip.id}>{value}</TooltipHint>}
  </InfoRow>;
}

function ChipCard({ chip, state }) {
  const place = useCardPlace();
  return state.card ? <PopoverContent {...place} collisionPadding={8} className={cn(POPOVER_CLASS, "w-56 max-w-[calc(100vw-1rem)]")}
    onOpenAutoFocus={event => event.preventDefault()} onCloseAutoFocus={event => event.preventDefault()}
    onPointerEnter={state.hover.stay} onPointerLeave={state.hover.leave} onInteractOutside={state.keepOnChip} data-quick-edit-ref-card={chip.key}>
    <CardTitle chip={chip} />
    <ScrollArea className="min-w-0" viewportProps={{ style: CARD_ROWS_STYLE }}>
      <div className="px-2 pb-1.5">
        {chip.id ? <IdRow chip={chip} /> : null}
        {chip.card}
      </div>
    </ScrollArea>
  </PopoverContent> : null;
}

function Chip({ chip }) {
  const state = useChip(chip);
  return <Popover open={state.hover.open} onOpenChange={state.hover.setOpen}>
    <PopoverAnchor asChild>
      <span className={CHIP_CLASS} {...state.surface}>
        <button className={cn(CHIP_LABEL_CLASS, state.copyable && "cursor-pointer")} {...state.label} />
        <RemoveButton chip={chip} />
      </span>
    </PopoverAnchor>
    <ChipCard chip={chip} state={state} />
  </Popover>;
}

// A row of "+N more": the chip, a line of the list, with its own card to the list's left.
function MoreChip({ chip }) {
  const state = useChip(chip);
  return <Popover open={state.hover.open} onOpenChange={state.hover.setOpen}>
    <PopoverAnchor asChild>
      <li className="flex h-6 min-w-0 items-center gap-1 rounded-sm pl-1.5 hover:bg-accent/50" {...state.surface}>
        <button className={cn("min-w-0 flex-1 truncate rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
          state.copyable ? "cursor-pointer" : "cursor-default")} {...state.label} />
        <RemoveButton chip={chip} />
      </li>
    </PopoverAnchor>
    <ChipCard chip={chip} state={state} />
  </Popover>;
}

// The rest, under one chip: a narrow list of them, each a chip in all but its look.
function MoreChips({ chips }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const place = useCardPlace();
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
      <button type="button" className={cn(CHIP_CLASS, CHIP_LABEL_CLASS, "text-muted-foreground hover:text-foreground")}
        data-quick-edit-ref-more="">{t("chip.more", { count: chips.length })}</button>
    </PopoverTrigger>
    <PopoverContent {...place} collisionPadding={8} className={cn(POPOVER_CLASS, "w-max min-w-28 max-w-44")}
      onOpenAutoFocus={event => event.preventDefault()} aria-label={t("chip.moreReferences")}>
      <ScrollArea className="min-w-0" viewportProps={{ style: LIST_STYLE }}>
        <ul className="flex flex-col p-1">
          {chips.map(chip => <MoreChip key={chip.key} chip={chip} />)}
        </ul>
      </ScrollArea>
    </PopoverContent>
  </Popover>;
}

/**
 * What a Quick Edit carries, as chips under its header: the first few, then "+N more" for the rest.
 * Each chip (a row of "+N more" too) names its picks, lights them in the view while the pointer is
 * on it, opens a card of what they are (their id first) on a rest of the pointer, copies their
 * reference on a click (and opens the card on a touch), and its X drops them from the selection. A
 * card's title copies the reference too, and a click on one of its values copies that value.
 *
 * Measure's row lists its measurements with these chips too (`measure/measurementChips.jsx`), named by `label`,
 * its cards opening `below` its chips rather than to their left, and as many chips as fit in `rows`
 * rows at its width before "+N more" (measured, again when the chips or the width change), rather
 * than a fixed few.
 *
 * @param {{ chips: readonly ReferenceChip[], className?: string, label?: string, below?: boolean, rows?: number }} props
 */
export default function ReferenceChips({ chips, className, label, below = false, rows = 0 }) {
  const { t } = useI18n();
  const box = useRef(null);
  const key = chips.map(chip => chip.key).join("\n");
  // With `rows`: how many chips fit in that many rows with "+N more" after them, for these chips.
  const [fit, setFit] = useState(null);
  const measured = rows && fit?.key === key ? fit.count : null;
  useLayoutEffect(() => {
    const element = box.current;
    if (!rows || !element) return;
    if (measured === null) {
      // Every chip is on the page, at the room it is given: the first one that starts a row past the
      // last allowed is where they stop, one before it to leave the room "+N more" takes.
      element.style.width = "";
      const tops = [...element.children].map(child => child.offsetTop);
      const lines = [...new Set(tops)].sort((a, b) => a - b);
      const past = lines.length > rows ? tops.findIndex(top => top >= lines[rows]) : -1;
      setFit({ key, count: past < 0 ? chips.length : Math.max(1, past - 1) });
      return;
    }
    // The chips kept, then as wide as their widest row, so what they sit in is no wider than they are.
    const left = element.getBoundingClientRect().left;
    const right = Math.max(...[...element.children].map(child => child.getBoundingClientRect().right));
    element.style.width = `${Math.ceil(right - left + parseFloat(getComputedStyle(element).paddingRight || "0"))}px`;
  });
  // A new width for the view measures them again.
  useEffect(() => {
    if (!rows) return undefined;
    const again = () => setFit(null);
    window.addEventListener("resize", again);
    return () => window.removeEventListener("resize", again);
  }, [rows]);
  if (!chips.length) return null;
  const count = rows ? measured ?? chips.length
    : chips.length > VISIBLE_REFERENCE_CHIPS + 1 ? VISIBLE_REFERENCE_CHIPS : chips.length;
  const shown = chips.slice(0, count);
  const rest = chips.slice(shown.length);
  return <ChipsBelowContext.Provider value={below}>
    <div ref={box} className={cn("flex min-w-0 flex-wrap gap-1", className)} aria-label={label ?? t("chip.references")} data-quick-edit-refs="">
      {shown.map(chip => <Chip key={chip.key} chip={chip} />)}
      {rest.length ? <MoreChips chips={rest} /> : null}
    </div>
  </ChipsBelowContext.Provider>;
}
