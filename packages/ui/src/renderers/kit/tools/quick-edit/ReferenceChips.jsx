import { createContext, isValidElement, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@cad/ui/primitives/popover";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { useViewerMobile } from "../../../../file-viewer/responsive.js";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { useCopyFlash } from "../../inspector/copyFlash.js";
import ItemDetail from "../../inspector/ItemDetail.jsx";
import { PickGlyph, compactSuffix, hasPickGlyph } from "../../inspector/pickGlyph.jsx";
import { useI18n } from "@cad/ui/i18n";

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
 * @property {string | (() => string)} [copy]  What a click on it copies: its reference, the file's path and its
 *   id; or a reference resolved at the click. Annotation and measurement chips omit this.
 * @property {import("../../inspector/inspect.js").DetailItem} [detail]  What it is, for its card: the view's description of
 *   it, the same the Selected pane draws (`ItemDetail.jsx`); its name, kind and facts.
 * @property {import("react").ReactNode} [icon]  Before its words: a measurement's ruler in its colour, the annotation's pen.
 * @property {string} [glyph]  Else, the glyph of what it names (`pickGlyph.jsx`: "solid" for a part, "face", "edge",
 *   "vertex", "ruler" for a measurement, "pencil" for the annotation); a compact name's own kind where it has none.
 * @property {string} [glyphColor]  The glyph's colour, where it has its own (a measurement's); else muted.
 * @property {string} [text]  The words beside an icon, where they are shorter than its accessible `label`.
 * @property {() => void} [onRemove]  Drops these picks from the selection.
 * @property {(on: boolean) => void} [onHover]  Lights these picks in the view while the pointer is on the chip.
 * @property {string} [group]  The kind of thing it names, which Quick Edit groups its chips by (`groupReferenceChips`):
 *   one of `CHIP_GROUPS`, the renderer's to say; absent, its glyph's (a solid's `part`, the pen's `drawing`).
 * @property {number} [count]  How many picks it stands for (a run of faces on one part), 1 when absent.
 */

/** The kinds Quick Edit's chips are grouped by, each with its count's words (`chip.group.<kind>`). */
export const CHIP_GROUPS = Object.freeze(["part", "face", "edge", "vertex", "drawing", "measurement", "component", "pad", "net", "track", "via",
  "zone", "area", "text", "pin", "label", "sheet", "wire", "link", "entity", "node", "object", "reference", "item"]);
const GLYPH_GROUPS = Object.freeze({ solid: "part", face: "face", edge: "edge", vertex: "vertex", pencil: "drawing", ruler: "measurement" });
export const chipGroup = chip => (CHIP_GROUPS.includes(chip.group) ? chip.group : GLYPH_GROUPS[chip.glyph ?? chip.compact?.kind] ?? "item");
export const chipCount = chip => Math.max(1, Number(chip.count ?? chip.compact?.count) || 1);

/**
 * Chips grouped by the kind of thing each names, in the order each kind first came: one group a kind, its
 * count the picks of that kind (a run of faces counts each face), its words that count ("5 parts", "3 faces",
 * `t`'s `chip.group.<kind>`), or, for a kind with a single pick, that pick's own name ("output_flange").
 * @param {readonly ReferenceChip[]} chips
 * @returns {{ key: string, group: string, glyph?: string, icon?: import("react").ReactNode, count: number, text: string, members: ReferenceChip[] }[]}
 */
export function groupReferenceChips(chips, t) {
  const groups = new Map();
  for (const chip of chips) {
    const group = chipGroup(chip);
    let entry = groups.get(group);
    if (!entry) groups.set(group, entry = { key: `group:${group}`, group, glyph: chip.glyph ?? chip.compact?.kind, icon: chip.icon, count: 0, members: [] });
    entry.count += chipCount(chip);
    entry.members.push(chip);
  }
  return [...groups.values()].map(entry => ({ ...entry,
    text: entry.count === 1 ? entry.members[0].text ?? entry.members[0].label : t(`chip.group.${entry.group}`, { count: entry.count }) }));
}

// What Quick Edit keeps apart from the geometry: the annotation and the measurements, each its own chip.
export const OWN_CHIPS = Object.freeze(["drawing", "measurement"]);

/**
 * Quick Edit's chips: every reference into the file, whatever a view picks (a part, a face, an edge, an item of a
 * sheet), is ONE chip — a single one by its name, several by their count ("5 refs", `quickEdit.refs`) — whose list (a
 * press, or a rest of the pointer) names each with its glyph, its kind and its X, its key facts under it, and whose X
 * drops them all; the annotation and the measurements stand beside it, their own chips.
 */
export function groupedChips(chips, t) {
  const geometry = chips.filter(chip => !OWN_CHIPS.includes(chipGroup(chip)));
  const count = geometry.reduce((sum, chip) => sum + chipCount(chip), 0);
  const merged = count > 1 ? {
    key: "group:references", label: t(count === 1 ? "quickEdit.ref" : "quickEdit.refs", { count }), glyph: geometry[0].glyph ?? geometry[0].compact?.kind,
    icon: geometry[0].icon, group: "reference", count, members: geometry,
    onRemove: geometry.some(member => member.onRemove) ? () => { for (const member of geometry) member.onRemove?.(); } : undefined,
    onHover: on => { for (const member of geometry) member.onHover?.(on); }
  } : null;
  // One reference alone is its own chip, by its name, its list that one's row.
  const single = count === 1 ? { ...geometry[0], members: [geometry[0]] } : null;
  const out = [];
  for (const chip of chips) {
    if (!OWN_CHIPS.includes(chipGroup(chip))) { const one = merged || single; if (!out.includes(one)) out.push(one); continue; }
    out.push(chip);
  }
  return out;
}

// A part's name on a chip is cut to this many characters, an ellipsis last: the chip's card (or, with
// none, its hint) gives the whole name.
export const CHIP_NAME_CHARS = 16;
export const capName = (name, chars = CHIP_NAME_CHARS) => (name.length > chars ? `${name.slice(0, chars - 1).trimEnd()}…` : name);

// The chips the box shows before the rest go under "+N more": one or two lines at the box's width.
export const VISIBLE_REFERENCE_CHIPS = 4;
// A card opens to the left of what it is the card of, over the view rather than over the chips
// under it. It follows the pointer onto a chip after a moment, and stays while the pointer is on
// it or its card. A click copies the chip's reference; a press with no pointer to rest (a touch,
// a key) opens the card too. A card is as tall as its rows, up to the room the view has.
const OPEN_DELAY_MS = 300;
const CLOSE_DELAY_MS = 150;
const CHIP_CLASS = "inline-flex h-5 min-w-0 max-w-full items-center rounded-sm bg-accent/70 text-xs text-foreground";
const CHIP_LABEL_CLASS = "min-w-0 truncate rounded-sm px-1.5 leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
const CHIP_REMOVE_CLASS = "cad-hit -ml-0.5 mr-0.5 flex size-glyph shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
const POPOVER_CLASS = cn(FLOATING_SURFACE_CLASS, "p-0 text-xs data-[state=closed]:animate-none!");
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
  const hinted = !chip.detail;
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
  const card = Boolean(chip.detail);
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
    onClick={() => { chip.onHover?.(false); chip.onRemove(); }}><X className="size-[calc(var(--cad-glyph)-6px)]" aria-hidden="true" /></button> : null;
}

// A chip's card: what the view says of it (`ItemDetail.jsx`), the one place a pick is read in detail.
// Quick Edit is a bar at the view's bottom, so a card opens above its chip, inside the view; where the
// chips hang "below", under the strip (Measure's row), every card opens under its chip.
const ChipsBelowContext = createContext(false);
// Quick Edit's cards name the pick alone: what it measures is its chip list's row (`GroupMember`).
const CardFactsContext = createContext(true);

function useCardPlace() {
  return useContext(ChipsBelowContext) ? { side: "bottom", align: "start", sideOffset: 6 } : { side: "top", align: "start", sideOffset: 8 };
}

// What a chip's card draws: the view's description of it (`detail`), named as the chip is where it has none.
const chipItem = chip => ({ id: chip.key, pick: "", kind: chip.glyph ?? chip.compact?.kind ?? "", facts: [], ...chip.detail,
  title: chip.detail?.title || chip.label });

// A row of the "+N more" list opens its card beside the list, not over the rows above it.
const BESIDE_LIST = { side: "right", align: "start", sideOffset: 8 };

function ChipCard({ chip, state, beside = false }) {
  const chipPlace = useCardPlace();
  const place = beside ? BESIDE_LIST : chipPlace;
  const facts = useContext(CardFactsContext);
  const item = useMemo(() => (facts ? chipItem(chip) : { ...chipItem(chip), facts: [] }), [chip, facts]);
  return state.card ? <PopoverContent {...place} collisionPadding={8} className={cn(POPOVER_CLASS, "w-64 max-w-[calc(100vw-1rem)]")}
    onOpenAutoFocus={event => event.preventDefault()} onCloseAutoFocus={event => event.preventDefault()}
    onPointerEnter={state.hover.stay} onPointerLeave={state.hover.leave} onInteractOutside={state.keepOnChip} data-quick-edit-ref-card={chip.key}>
    <ScrollArea className="min-w-0" viewportProps={{ style: LIST_STYLE }}>
      <ItemDetail item={item} copy={chip.copy || null} />
    </ScrollArea>
  </PopoverContent> : null;
}

function Chip({ chip }) {
  if (chip.members) return <GroupChip chip={chip} />;
  return <OneChip chip={chip} />;
}

// A group of several picks of one kind: its count, its list on a rest of the pointer or a press, its X dropping them all.
function GroupChip({ chip }) {
  const { t } = useI18n();
  const hover = useHoverOpen(true);
  const place = useCardPlace();
  return <Popover open={hover.open} onOpenChange={hover.setOpen}>
    <PopoverAnchor asChild>
      <span className={CHIP_CLASS} data-quick-edit-ref={chip.key} data-quick-edit-group={chip.group}
        onPointerEnter={event => { if (event.pointerType === "mouse") chip.onHover?.(true); hover.enter(event); }}
        onPointerLeave={event => { if (event.pointerType === "mouse") chip.onHover?.(false); hover.leave(event); }}>
        <button type="button" className={cn(CHIP_LABEL_CLASS, "cursor-pointer")} aria-label={chip.label} aria-haspopup="dialog" aria-expanded={hover.open}
          onClick={() => hover.setOpen(open => !open)}><ChipText chip={chip} /></button>
        <RemoveButton chip={chip} />
      </span>
    </PopoverAnchor>
    <PopoverContent {...place} collisionPadding={8} className={cn(POPOVER_CLASS, "w-max min-w-40 max-w-72")} aria-label={t("chip.groupList", { name: chip.label })}
      onOpenAutoFocus={event => event.preventDefault()} onCloseAutoFocus={event => event.preventDefault()}
      onPointerEnter={hover.stay} onPointerLeave={hover.leave} data-quick-edit-group-list={chip.group}>
      <ScrollArea className="min-w-0" viewportProps={{ style: LIST_STYLE }}>
        <ul className="flex flex-col p-1">{chip.members.map(member => <GroupMember key={member.key} chip={member} />)}</ul>
      </ScrollArea>
    </PopoverContent>
  </Popover>;
}

// A row of a reference chip's list: the reference — its glyph, its name and its kind ("Part", "Face of output_flange") —
// and its X, lighting its picks while the pointer is on it; under it, its key facts (`ReferenceFacts`). A press on its
// name copies its reference, "Copied" in the name's place for a moment.
function GroupMember({ chip }) {
  const { t } = useI18n();
  const flash = useCopyFlash();
  const copyable = Boolean(chip.copy) && flash.canCopy;
  const copied = copyable && flash.copied;
  const name = chip.detail?.title || chip.label;
  return <li className="flex min-w-0 flex-col rounded-sm hover:bg-accent/50" data-quick-edit-group-member={chip.key}
    onPointerEnter={event => { if (event.pointerType === "mouse") chip.onHover?.(true); }}
    onPointerLeave={event => { if (event.pointerType === "mouse") chip.onHover?.(false); }}>
    <div className="flex h-icon-button min-w-0 items-center gap-1 pl-1.5">
      <button type="button" aria-label={chip.label} className={cn("flex min-w-0 flex-1 items-center gap-1.5 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
        copyable ? "cursor-pointer" : "cursor-default")} onClick={() => { if (copyable) void copyChip(flash, chip); }} data-quick-edit-group-show="">
        {copied ? <span className="inline-flex items-center gap-1"><Check className="size-2.5" aria-hidden="true" />{t("chip.copied")}</span>
          : <ReferenceName chip={chip} name={name} />}
        <span className="shrink-0 text-tiny text-muted-foreground" data-quick-edit-ref-kind="">{referenceKind(chip, t)}</span>
      </button>
      <RemoveButton chip={chip} />
    </div>
    <ReferenceFacts facts={chip.detail?.facts} />
  </li>;
}

// A row's reference: its icon, then its whole name (never cut to a chip's length: the list is where it is read whole),
// truncated only where the list's width runs out.
function ReferenceName({ chip, name }) {
  const glyph = chip.glyph ?? chip.compact?.kind;
  const icon = chip.icon ?? (hasPickGlyph(glyph)
    ? <PickGlyph kind={glyph} color={chip.glyphColor} className={cn("size-2.5 shrink-0", !chip.glyphColor && "text-muted-foreground")} /> : null);
  return <span className="inline-flex min-w-0 items-center gap-1" data-quick-edit-ref-name="">{icon}<span className="min-w-0 truncate" title={name}>{name}</span></span>;
}

/** A reference's kind, as its row names it: "Part", "Face of output_flange", "6 faces". */
export function referenceKind(chip, t) {
  const group = chipGroup(chip);
  if (chipCount(chip) > 1) return t(`chip.group.${group}`, { count: chipCount(chip) });
  const owner = chip.compact?.name && ["face", "edge", "vertex"].includes(chip.compact.kind) ? String(chip.compact.name) : "";
  return owner ? t("inspector.kindOf", { kind: t(`inspector.kind.${group}`), owner }) : t(`inspector.kind.${group}`);
}

/** Text a fact can draw as it is: a string, or a finite number. */
const plainText = value => typeof value === "string" || (typeof value === "number" && Number.isFinite(value));

/**
 * The facts a reference's row draws: those with a label that is text and a value that is text or an element (a
 * coordinate's); one that is not is left out, and said, so one bad value never takes the view down.
 * @param {unknown} facts
 */
export function referenceFacts(facts) {
  return (Array.isArray(facts) ? facts : []).filter(fact => {
    const ok = Boolean(fact) && plainText(fact.label) && (plainText(fact.value) && String(fact.value) !== "" || isValidElement(fact.value));
    if (!ok && fact && fact.value !== "" && fact.value != null) console.warn("[cad] a reference's fact that is not text was left out", fact);
    return ok;
  });
}

/**
 * A reference's key facts under its row, as the view describes it (its chip's `detail.facts`, the view's own producers:
 * a part's size, volume and mass; a face's type and area; an edge's length or radius; a board part's value, footprint
 * and net…), only those it knows, in the muted 11/16: the labels in a first column as wide as its longest, the values
 * after them in tabular figures, under the name.
 */
function ReferenceFacts({ facts }) {
  const shown = referenceFacts(facts);
  return shown.length ? <dl className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-2 pr-2 pb-1 pl-5 text-tiny leading-(--cad-leading-xs) text-muted-foreground" data-quick-edit-ref-facts="">
    {shown.map(fact => <div key={String(fact.label)} className="contents">
      <dt className="whitespace-nowrap">{String(fact.label)}</dt>
      <dd className="min-w-0 tabular-nums [overflow-wrap:anywhere]">{plainText(fact.value) ? String(fact.value) : fact.value}</dd>
    </div>)}
  </dl> : null;
}

function OneChip({ chip }) {
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

// A row of "+N more": the chip, a line of the list, with its own card beside the list.
function MoreChip({ chip }) {
  const state = useChip(chip);
  return <Popover open={state.hover.open} onOpenChange={state.hover.setOpen}>
    <PopoverAnchor asChild>
      <li className="flex h-icon-button min-w-0 items-center gap-1 rounded-sm pl-1.5 hover:bg-accent/50" {...state.surface}>
        <button className={cn("min-w-0 flex-1 truncate rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
          state.copyable ? "cursor-pointer" : "cursor-default")} {...state.label} />
        <RemoveButton chip={chip} />
      </li>
    </PopoverAnchor>
    <ChipCard chip={chip} state={state} beside />
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
 * Quick Edit's chips are `grouped` (`groupedChips`: the references one chip, a single one by its name), and that chip's
 * list names each reference with its kind and its key facts under it.
 *
 * @param {{ chips: readonly ReferenceChip[], className?: string, label?: string, below?: boolean, rows?: number, grouped?: boolean }} props
 */
export default function ReferenceChips({ chips: given, className, label, below = false, rows = 0, grouped = false }) {
  const { t } = useI18n();
  const chips = useMemo(() => (grouped ? groupedChips(given, t) : given), [given, grouped, t]);
  const box = useRef(null);
  const key = chips.map(chip => `${chip.key}:${chip.count ?? 1}`).join("\n");
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
  // A new width for the room they stand in (the view's, or the bar's as the panel opens or closes)
  // measures them again.
  useEffect(() => {
    const room = box.current?.parentElement;
    if (!rows || !room) return undefined;
    const again = () => setFit(null);
    window.addEventListener("resize", again);
    let width = room.clientWidth;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      if (room.clientWidth !== width) { width = room.clientWidth; again(); }
    });
    observer?.observe(room);
    return () => { window.removeEventListener("resize", again); observer?.disconnect(); };
  }, [rows]);
  if (!chips.length) return null;
  const count = rows ? measured ?? chips.length
    : chips.length > VISIBLE_REFERENCE_CHIPS + 1 ? VISIBLE_REFERENCE_CHIPS : chips.length;
  const shown = chips.slice(0, count);
  const rest = chips.slice(shown.length);
  return <ChipsBelowContext.Provider value={below}><CardFactsContext.Provider value={!grouped}>
    <div ref={box} className={cn("flex min-w-0 flex-wrap gap-1", className)} aria-label={label ?? t("chip.references")} data-quick-edit-refs="">
      {shown.map(chip => <Chip key={chip.key} chip={chip} />)}
      {rest.length ? <MoreChips chips={rest} /> : null}
    </div>
  </CardFactsContext.Provider></ChipsBelowContext.Provider>;
}
