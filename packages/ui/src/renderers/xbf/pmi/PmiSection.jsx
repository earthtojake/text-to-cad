import { Fragment, useContext, useEffect, useMemo, useRef, useState } from "react";
import { CircleAlert, Eye, EyeOff, Pin, Plus } from "lucide-react";
import { pmiCallText, pmiNumber, pmiToleranceText } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { ROW_NAME_UNDER_ACTIONS, TreeRowLabel, TreeRowSurface, treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { cn } from "@text-to-cad/ui/utils";
import { useI18n } from "@text-to-cad/ui/i18n";
import { FileSheetSettingsSection, FileSheetStatusText, FileSheetValueInput } from "../../kit/inspector/FileSheet.js";
import { InfoRow, MonoValue } from "../../kit/inspector/referenceRows.jsx";
import ToolPanel, { TOOL_PANEL_BUTTON_CLASS, ToolPanelHeadAction } from "../../kit/tools/ToolPanel.jsx";
import { ToolStackContext } from "../../kit/tools/ToolStack.jsx";
import { PmiGlyph, PmiIcon } from "./pmiGlyphs.jsx";
import { MAX_DATUMS, datumLetters, newPmiName, parseToleranceInput, pmiCreateOptions, toggleDatum } from "./pmiCreate.js";
import { datumDependents, datumRelationships, dimensionLimits, featureRequirements } from "./pmiReview.js";
import { PMI_SECTION_OFF, pmiViewShowsText } from "./pmiViews.js";

// An engine document's **PMI**, a section of the file sidebar for a document that carries any, read
// as a machinist reads a drawing (its model-based definition): under static headings, nothing
// folding, its **Views** -- each part's named views, a row each, its name and what it shows; a pick
// applies one (`usePmiViewApplied`: its camera and section, and only its PMI drawn, where it
// places it) and a second leaves it --, its **Notes** in their numbers (the general profile Note
// 1, a flag note with its flag, lit on its faces when picked), its **Coverage** (how many faces no
// requirement is on, which a checkbox lights, each requirement that cannot hold with another, a
// warning, and each question the requirements leave open, with the standard answer the engine
// suggests and, on hover, why: asked, never applied), then its **Annotations**: every one, a row each -- its glyph and what its callout
// says, and its eye -- in the document's order. The one picked opens under its row, its values
// read out with their units and where each came from (a nominal measured on the geometry or as
// another system's file gives it, a tolerance as the code gave it, or none given), its references
// and how they stand, where it is placed; an annotation the viewer does
// not draw is a row too, saying why. Its head holds New (what the faces Select has picked can be)
// and the eye of them all. Where the document is made from code the agent can change, a value
// edited here, a label moved in the view, a placement pinned or a new annotation is a change Quick
// Edit carries to the agent (`useXbfPmi`): nothing here writes the file. A row is an annotation's
// `key` (its part's and its id), and says its id; a view's row is its own, never an annotation's.
// Every word it says reads through the locale files (`pmi.*`); what the engine and the document
// say (a callout, a reference's status, a conflict) is said as they give it.

const EMPTY = Object.freeze([]);
const ROW_ACTIONS_WIDTH = "1.5rem";
const ROLE_KEYS = Object.freeze({ feature: "pmi.role.feature", from: "pmi.role.from", to: "pmi.role.to" });
const STATUS_KEYS = Object.freeze({ missing: "pmi.status.missing", ambiguous: "pmi.status.ambiguous", invalid: "pmi.status.invalid" });
// A frame's datums in their order (`datumRelationships`'s `role`).
const DATUM_ROLE_KEYS = Object.freeze({ Primary: "pmi.datumRole.primary", Secondary: "pmi.datumRole.secondary", Tertiary: "pmi.datumRole.tertiary" });
const STATUS_TEXT = Object.freeze({ missing: "text-destructive", invalid: "text-destructive", ambiguous: "text-amber-500" });
// A requirement that cannot hold with another: in a warning's colour, as an ambiguous reference is.
const WARNING_TEXT = STATUS_TEXT.ambiguous;
// Where a nominal came from: measured on the geometry by the engine, or as another system's file gives it.
const NOMINAL_SOURCE = Object.freeze({ geometry: { said: "pmi.nominal.measured", about: "pmi.nominal.measuredHint" },
  file: { said: "pmi.nominal.fromFile", about: "pmi.nominal.fromFileHint" } });
const mm = (value, unit = "mm") => `${value} ${unit}`;
// What the list follows: the faces, edges and vertices of a selection, as one key.
const selectionKeyOf = ids => JSON.stringify(ids);
// Drawn on the part, so its eye hides it: what is said in the notes alone is not.
const drawnKind = entry => entry.drawable ?? entry.supported;
const ROW_BUTTON = "flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-1 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** A requirement that cannot hold with another: in a warning's colour. */
function Warning({ children, ...props }) {
  return <p className={cn("flex items-start gap-1 py-0.5 text-tiny", WARNING_TEXT)} role="status" data-pmi-warning="" {...props}>
    <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" /><span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
  </p>;
}

function RowEye({ entry, hidden, onToggle }) {
  const { t } = useI18n();
  const action = t(hidden ? "tree.reveal" : "tree.hide");
  return <div data-row-actions="" className={treeRowActionsClass(hidden)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={`${action} ${entry.id}`} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-pmi-visibility={entry.id} onClick={event => { event.stopPropagation(); onToggle(entry.key); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </div>;
}

const toleranceInputText = tolerance => (tolerance ? pmiToleranceText(tolerance).text : "");

function ToleranceField({ value, onCommit, label = "" }) {
  const { t } = useI18n();
  label ||= t("pmi.tolerance");
  const [error, setError] = useState("");
  return <>
    <div className="flex items-center justify-between gap-3 py-0.5">
      <span className="shrink-0 text-tiny text-muted-foreground">{label}</span>
      <FileSheetValueInput value={toleranceInputText(value)} ariaLabel={label} inputMode="text" className="w-20 min-w-0"
        onValueCommit={(text) => {
          const read = parseToleranceInput(text, t);
          setError(read.error || "");
          if (!read.error) onCommit(read.tolerance);
        }} />
    </div>
    {error ? <p role="alert" className="text-tiny text-destructive">{error}</p> : null}
  </>;
}

function ValueField({ value, onCommit, label }) {
  const { t } = useI18n();
  const [error, setError] = useState("");
  return <>
    <div className="flex items-center justify-between gap-3 py-0.5">
      <span className="shrink-0 text-tiny text-muted-foreground">{label}</span>
      <FileSheetValueInput value={value === null || value === undefined ? "" : pmiNumber(value)} ariaLabel={label} className="w-16 min-w-0"
        onValueCommit={(text) => {
          const number = Number(String(text).trim());
          if (!String(text).trim()) { setError(""); onCommit(null); return; }
          if (!(Number.isFinite(number) && number > 0)) { setError(t("pmi.error.toleranceValue")); return; }
          setError("");
          onCommit(number);
        }} />
    </div>
    {error ? <p role="alert" className="text-tiny text-destructive">{error}</p> : null}
  </>;
}

function DatumPicker({ letters, value, onChange }) {
  const { t } = useI18n();
  if (!letters.length) return null;
  return <div className="flex items-center justify-between gap-3 py-0.5">
    <span className="shrink-0 text-tiny text-muted-foreground">{t("pmi.datums")}</span>
    <div className="flex flex-wrap justify-end gap-1">
      {/* In the order picked, primary first (a frame's order is what it means), at most three. */}
      {letters.map(letter => <button key={letter} type="button" aria-pressed={value.includes(letter)} data-pmi-datum-choice={letter}
        disabled={!value.includes(letter) && value.length >= MAX_DATUMS}
        onClick={() => onChange(toggleDatum(value, letter))}
        className={cn("h-5 min-w-5 rounded-sm border px-1 text-tiny", value.includes(letter) ? "border-foreground bg-accent text-foreground" : "border-border text-muted-foreground")}>
        {letter}
      </button>)}
    </div>
  </div>;
}

/** The values of an annotation, read out: what it is, and where every number came from. */
function EntryDetails({ entry, pmi, onSelectRelated }) {
  const { t } = useI18n();
  const editable = pmi.editable && entry.supported && entry.status === "ok";
  const construction = pmi.constructions.get(entry.key);
  const pending = pmi.changes.find(change => change.key === `edit:${entry.key}`);
  const values = pending?.values || {};
  const given = key => (Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined);
  const limits = dimensionLimits(entry);
  const datumLinks = datumRelationships(entry, pmi.entries);
  const dependents = datumDependents(entry, pmi.entries);
  return <div className="px-2 pb-1.5 pt-0.5" data-pmi-details={entry.id}>
    {entry.statusText ? <p className={cn("flex items-start gap-1 py-0.5 text-tiny", STATUS_TEXT[entry.status])} role="status">
      <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" /><span className="min-w-0 [overflow-wrap:anywhere]">{entry.statusText}</span>
    </p> : null}
    {!entry.supported ? <FileSheetStatusText className="px-0">{t("pmi.notShownReason", { reason: entry.unsupported })}</FileSheetStatusText> : null}
    {!entry.supported ? (entry.values || []).slice(0, 8).map(([key, value]) => <InfoRow key={key} label={key} copy={false}>{value}</InfoRow>) : null}
    {entry.kind === "dimension" && entry.supported ? <>
      {entry.dimension.nominal === null ? <InfoRow label={t("pmi.nominal")} copy={false}>{t("pmi.nominalUnknown")}</InfoRow>
        : <InfoRow label={t("pmi.nominal")} title={NOMINAL_SOURCE[entry.dimension.source] ? t(NOMINAL_SOURCE[entry.dimension.source].about) : undefined}><MonoValue>{mm(entry.callout.diameter ? `⌀${pmiNumber(entry.dimension.nominal, 3)}` : pmiNumber(entry.dimension.nominal, 3), entry.dimension.unit)}</MonoValue>
          <span className="text-muted-foreground">{NOMINAL_SOURCE[entry.dimension.source] ? t(NOMINAL_SOURCE[entry.dimension.source].said) : ""}</span></InfoRow>}
      {entry.dimension.basic ? <InfoRow label={t("pmi.tolerance")} copy={false}>{t("pmi.basicExact")}</InfoRow>
        : editable ? <ToleranceField value={given("tolerance") === undefined ? entry.dimension.tolerance : given("tolerance")}
        onCommit={tolerance => pmi.edit(entry.key, { tolerance })} />
        : <InfoRow label={t("pmi.tolerance")}>{entry.dimension.tolerance ? <MonoValue>{mm(pmiToleranceText(entry.dimension.tolerance).text, entry.dimension.unit)}</MonoValue> : t("pmi.noneGiven")}</InfoRow>}
      {limits ? <InfoRow label={t("pmi.currentLimits")} copy={false}><MonoValue>{mm(`${pmiNumber(limits.lower, limits.places)}–${pmiNumber(limits.upper, limits.places)}`, limits.unit)}</MonoValue></InfoRow> : null}
    </> : null}
    {entry.kind === "datum" && entry.supported ? <InfoRow label={t("pmi.letter")}>{entry.datum.letter}</InfoRow> : null}
    {entry.kind === "note" && entry.supported ? <>
      <p className="py-0.5 text-tiny text-foreground [overflow-wrap:anywhere]" data-pmi-note-text="">{entry.note.text}</p>
      {entry.note.annotations.length ? <InfoRow label={t("pmi.annotations")} copy={false}>{entry.note.annotations.join(", ")}</InfoRow> : null}
    </> : null}
    {entry.kind === "geometric_tolerance" && entry.supported ? <>
      {/* The general profile is its part's Note 1, on every face nothing else controls (its faces below). */}
      <InfoRow label={t("pmi.kind")}>{entry.tolerance.general ? t("pmi.option.general_profile") : entry.callout.title}</InfoRow>
      {editable ? <ValueField label={t("pmi.tolerance")} value={given("value") ?? entry.tolerance.value} onCommit={value => { if (value !== null) pmi.edit(entry.key, { value }); }} />
        : <InfoRow label={t("pmi.tolerance")}><MonoValue>{mm(`${entry.tolerance.zone === "diameter" ? "⌀" : ""}${pmiNumber(entry.tolerance.value)}`, entry.tolerance.unit)}</MonoValue></InfoRow>}
      {entry.tolerance.characteristic === "position" && editable
        ? <DatumPicker letters={datumLetters(pmi.entries, entry.part)} value={given("datums") ?? entry.tolerance.datums} onChange={datums => pmi.edit(entry.key, { datums })} />
        : entry.tolerance.characteristic !== "flatness" ? <InfoRow label={t("pmi.datums")}>{entry.tolerance.datums.join(", ") || t("pmi.none")}</InfoRow> : null}
    </> : null}
    {datumLinks.length ? <div className="py-1" role="group" aria-label={t("pmi.highlightDatums")}>
      <p className="pb-1 text-tiny text-muted-foreground">{t("pmi.highlightDatums")}</p>
      {datumLinks.map(({ letter, role, entry: datum }) => <button key={letter} type="button"
        aria-label={t("pmi.highlightDatum", { role: t(DATUM_ROLE_KEYS[role]).toLowerCase(), letter })} aria-pressed={Boolean(datum && pmi.datumFocus === datum.key)}
        disabled={!datum || datum.status !== "ok"} onClick={() => pmi.focusDatum(datum.key)}
        className="flex h-6 w-full items-center justify-between gap-2 rounded px-1 text-tiny hover:bg-accent aria-pressed:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
        <span>{t(DATUM_ROLE_KEYS[role])}</span><span>{letter}</span>
      </button>)}
    </div> : null}
    {dependents.length ? <div className="py-1 text-tiny"><p className="pb-1 text-muted-foreground">{t("pmi.usedBy")}</p>
      {dependents.map(item => <button key={item.key} type="button" className="block w-full rounded px-1 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => onSelectRelated(item)}>{item.callout.text}</button>)}
    </div> : null}
    {entry.refs.map(ref => <InfoRow key={`${ref.role}:${ref.ref}`} label={ROLE_KEYS[ref.role] ? t(ROLE_KEYS[ref.role]) : ref.role} copy={ref.ref}
      title={ref.status === "ok" ? ref.ref : `${t(STATUS_KEYS[ref.status])}: ${ref.written}`}>
      <span className={cn("[overflow-wrap:anywhere]", STATUS_TEXT[ref.status])}>{ref.status === "ok" ? ref.name : ref.written}</span>
      {ref.status === "ambiguous" && ref.candidates.length ? <span className="block text-muted-foreground">{t("pmi.names", { candidates: ref.candidates.join(", ") })}</span> : null}
    </InfoRow>)}
    {drawnKind(entry) ? <InfoRow label={t("pmi.placed")} copy={false}>{pmi.view?.place?.[entry.id] && pmi.view.part === entry.part ? t("pmi.placedInView", { name: pmi.view.name })
      : t(pending?.values.presentation ? "pmi.placedMoved" : entry.presentation ? "pmi.placedInCode" : "pmi.placedBeside")}</InfoRow> : null}
    {editable && (pmi.placeable ?? true) && construction && !entry.presentation && !pending?.values.presentation ? <Button type="button" variant="ghost" size="xs" className="-ml-1.5 h-6 text-tiny"
      data-pmi-pin={entry.id} onClick={() => pmi.pin(entry.key)}><Pin className="size-3" aria-hidden="true" />{t("pmi.pin")}</Button> : null}
    {pending ? <FileSheetStatusText className="px-0">{t("pmi.pending")}</FileSheetStatusText> : null}
  </div>;
}

// A new annotation's glyph: a distance's, basic or not, is a dimension's; a profile's, general or
// not, the surface profile's; a note's, its flag.
const OPTION_GLYPHS = Object.freeze({ distance: "dimension", basic: "dimension", profile: "surface_profile", general_profile: "surface_profile", note: "flag" });
const optionGlyph = kind => OPTION_GLYPHS[kind] || kind;

/** A word field of a new one (a note's text, a view's name): its label, then the field filling the row. */
function TextField({ label, ariaLabel, value, onCommit, error = "" }) {
  return <>
    <div className="flex items-center justify-between gap-3 py-0.5">
      <span className="shrink-0 text-tiny text-muted-foreground">{label}</span>
      <FileSheetValueInput value={value} ariaLabel={ariaLabel} inputMode="text" className="min-w-0 flex-1 text-left" onValueCommit={text => onCommit(String(text).trim())} />
    </div>
    {error ? <p role="alert" className="text-tiny text-destructive">{error}</p> : null}
  </>;
}

/** A view's section in words: the Clip's axis and where it stands, and whether it keeps the upper side (the Clip's Reverse). */
const sectionText = (section, t) => t(section.invert ? "pmi.sectionAtReversed" : "pmi.sectionAt", { axis: section.axis.toUpperCase(), at: pmiNumber(section.at) });

/**
 * A new annotation being made: its kind's values to give, then Add to Quick Edit, once the call has
 * what its kind needs (`pmiCallText`). A position's and a profile's datums are its part's; a note's
 * words are typed; a view, seen from here, is named
 * afresh and can be renamed, and says why where it is refused (`option.problem`).
 */
function NewEntry({ option, onAdd, onCancel }) {
  const { t } = useI18n();
  const [call, setCall] = useState(option.call);
  const [nameError, setNameError] = useState("");
  const needsValue = call.kind === "geometric_tolerance";
  const ready = !option.problem && pmiCallText(call) !== null;
  const rename = (name) => {
    const problem = !name ? t("pmi.error.viewName") : name !== call.name && option.names.includes(name) ? t("pmi.error.viewNameTaken") : "";
    setNameError(problem);
    if (!problem) setCall(now => ({ ...now, name }));
  };
  const write = text => setCall(now => (text === now.text ? now : { ...now, text }));
  return <div className="border-b border-border px-2 pb-2 pt-1" data-pmi-new={option.kind}>
    <p className="flex items-center gap-1.5 py-0.5 text-tiny text-foreground"><PmiGlyph name={optionGlyph(option.kind)} className="size-3" aria-hidden="true" />
      {t("pmi.newNamed", { name: newPmiName(call, t) })}</p>
    {option.nominal !== null && option.nominal !== undefined ? <InfoRow label={t("pmi.nominal")} title={t("pmi.nominalMeshHint")} copy={false}>
      <MonoValue>{mm(pmiNumber(option.nominal, 3))}</MonoValue><span className="text-muted-foreground">{t("pmi.nominal.measured")}</span></InfoRow> : null}
    {call.kind === "dimension" && !call.basic ? <ToleranceField value={call.tolerance} onCommit={tolerance => setCall(now => ({ ...now, tolerance }))} /> : null}
    {needsValue ? <ValueField label={t("pmi.tolerance")} value={call.value} onCommit={value => setCall(now => ({ ...now, value }))} /> : null}
    {call.characteristic === "position" || call.characteristic === "surface_profile"
      ? <DatumPicker letters={option.datums} value={call.datums} onChange={datums => setCall(now => ({ ...now, datums }))} /> : null}
    {call.kind === "note" ? <>
      <TextField label={t("pmi.text")} ariaLabel={t("pmi.noteText")} value={call.text} onCommit={write} />
      <FileSheetStatusText className="px-0">{t(call.faces.length ? "pmi.flagNote" : "pmi.generalNote")}</FileSheetStatusText>
    </> : null}
    {call.kind === "view" ? <>
      <TextField label={t("pmi.name")} ariaLabel={t("pmi.viewName")} value={call.name} onCommit={rename} error={nameError} />
      {option.problem ? <FileSheetStatusText className="px-0">{option.problem}</FileSheetStatusText> : <>
        <InfoRow label={t("pmi.shows")} copy={false}>{pmiViewShowsText(call, t)}</InfoRow>
        <InfoRow label={t("pmi.section")} copy={false}>{call.section ? sectionText(call.section, t) : t("pmi.none")}</InfoRow>
      </>}
    </> : null}
    {call.kind === "dimension" && call.basic ? <FileSheetStatusText className="px-0">{t("pmi.basicNoTolerance")}</FileSheetStatusText>
      : call.kind === "dimension" && !call.tolerance ? <FileSheetStatusText className="px-0">{t("pmi.noTolerance")}</FileSheetStatusText> : null}
    <div className="flex justify-end gap-1.5 pt-1">
      <Button type="button" variant="ghost" size="xs" className="h-6 text-tiny" onClick={onCancel}>{t("pmi.cancel")}</Button>
      <Button type="button" size="xs" className="h-6 text-tiny" disabled={!ready} onClick={() => onAdd(call)} data-pmi-add="">{t("pmi.addToQuickEdit")}</Button>
    </div>
  </div>;
}

/**
 * An annotation's or a note's row: its glyph (a 12px column; a general note's empty), what it says
 * (`children`) and its eye where it is drawn on the part; picked, its values open under it.
 */
function EntryRow({ entry, pmi, label, rowProps, onSelectRelated, children }) {
  const { t } = useI18n();
  const hidden = pmi.hiddenKeys.includes(entry.key);
  const picked = entry.key === pmi.selectedKey;
  return <li className="min-w-0">
    <TreeRowSurface dense active={picked} className="group/row gap-0 pr-0" style={{ "--row-actions": ROW_ACTIONS_WIDTH }} {...rowProps}
      onMouseEnter={() => pmi.hover(entry.key)} onMouseLeave={() => pmi.hover("")}>
      <button type="button" aria-pressed={picked} aria-label={`${label}${entry.statusText ? `: ${entry.statusText}` : ""}`} data-pmi-pick={entry.id}
        onClick={() => pmi.select(picked ? "" : entry.key)}
        className={cn(ROW_BUTTON, (hidden || !entry.supported) && "text-muted-foreground",
          drawnKind(entry) && (hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
        {entry.glyph ? <PmiGlyph name={entry.glyph} className="size-3 shrink-0" aria-hidden="true" /> : <span className="size-3 shrink-0" aria-hidden="true" />}
        {children}
        {entry.status !== "ok" ? <CircleAlert className={cn("size-3 shrink-0", STATUS_TEXT[entry.status])} aria-label={t(STATUS_KEYS[entry.status])} /> : null}
      </button>
      {drawnKind(entry) ? <RowEye entry={entry} hidden={hidden} onToggle={pmi.toggleHidden} /> : null}
    </TreeRowSurface>
    {picked ? <EntryDetails entry={entry} pmi={pmi} onSelectRelated={onSelectRelated} /> : null}
  </li>;
}

/**
 * A part's named view: its glyph, its name and what it shows (how many, or all), and its part where
 * several parts have views (`ofParts`); a pick applies it, a second leaves it. One its part's
 * placement cannot cut, or the viewer cannot apply, says why.
 */
function ViewRow({ view, pmi, ofParts }) {
  const { t } = useI18n();
  const active = view.key === pmi.viewKey;
  const note = !view.supported ? t("pmi.notShownReason", { reason: view.unsupported }) : view.at?.sectionOff ? t(PMI_SECTION_OFF) : "";
  return <li className="min-w-0">
    <TreeRowSurface dense active={active} className="gap-0 pr-0" data-pmi-view={view.name}>
      <button type="button" aria-pressed={active} aria-label={`${view.name}${note ? `: ${note}` : ""}`} disabled={!view.at}
        onClick={() => pmi.chooseView(view.key)} className={cn(ROW_BUTTON, !view.at && "text-muted-foreground")}>
        <PmiGlyph name="view" className="size-3 shrink-0" aria-hidden="true" />
        <TreeRowLabel className="min-w-0 shrink">{view.name}</TreeRowLabel>
        <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{view.supported ? pmiViewShowsText(view, t) : t("pmi.notShown")}</TreeRowLabel>
        {ofParts ? <TreeRowLabel className="shrink-0 text-micro text-muted-foreground">{view.partName}</TreeRowLabel> : null}
      </button>
    </TreeRowSurface>
    {note ? <FileSheetStatusText className="pb-0.5 pl-6">{note}</FileSheetStatusText> : null}
  </li>;
}

// New lists what is of the faces' part after what stands on them, from the note on (a flag note on
// them where there are any; its general profile; a view from here), in one place whatever is picked.
const FIRST_OF_PART = "note";

// What coverage found of a part, in words: how many of its faces no requirement is on.
const uncoveredText = (count, t) => (!count ? t("pmi.coverageAll") : t(count === 1 ? "pmi.coverageOne" : "pmi.coverageMany", { count }));

/**
 * @param {{ pmi: ReturnType<typeof import("./useXbfPmi.jsx").useXbfPmi>, picked: Parameters<typeof pmiCreateOptions>[0]["picked"],
 *   selectedFeatureIds?: readonly string[], moving: boolean, request?: { kind: string, key: number } | null,
 *   onRequestDone?: () => void }} props
 *   `picked`: the faces Select has picked, what New can make of; `selectedFeatureIds`: the faces,
 *   edges and vertices Select has picked, whose requirements the list narrows to while no
 *   annotation is picked; `moving`: the parts stand elsewhere than built, so the PMI is not drawn;
 *   `request`: a kind asked for from a face's menu ("Add datum"), which opens the section on its
 *   form; `onRequestDone`: the form has gone (added or cancelled).
 */
export default function PmiSection({ pmi, picked, selectedFeatureIds = EMPTY, moving, request = null, onRequestDone }) {
  const { t } = useI18n();
  // What is already asked for counts as taken: a second new one never reuses a pending id, letter or name.
  const options = useMemo(() => pmiCreateOptions({ picked, entries: pmi.entries, pending: pmi.pending, parts: pmi.parts, views: pmi.views,
    moving, t }), [picked, pmi.entries, pmi.pending, pmi.parts, pmi.views, moving, t]);
  const [draft, setDraft] = useState(null);
  // Each choice is a form of its own (`started`); a view is seen from where the viewport looks as it is chosen.
  const started = useRef(0);
  const begin = (option) => {
    started.current += 1;
    setDraft({ ...option, ...(option.kind === "view" ? pmi.viewFromHere(option.part, option.call.name) : null), started: started.current });
  };
  const featureIds = pmi.selectedEntry ? pmi.selectedEntry.featureIds : selectedFeatureIds;
  const selectionKey = selectionKeyOf(featureIds);
  const [showAllFor, setShowAllFor] = useState("");
  const filtered = featureIds.length > 0 && showAllFor !== selectionKey;
  // The notes are listed in their numbers, under Notes; the annotations are the rest.
  const views = pmi.views || EMPTY;
  const notes = pmi.notes || EMPTY;
  const coverage = pmi.coverage || EMPTY;
  const annotations = useMemo(() => {
    const said = new Set(notes.map(note => note.key));
    return pmi.entries.filter(entry => !said.has(entry.key));
  }, [pmi.entries, notes]);
  const visible = filtered ? featureRequirements(annotations, featureIds) : annotations;
  // Notes of several parts each number from 1, and views of several may share a name: each says its part.
  const notesOfParts = new Set(notes.map(note => note.part)).size > 1;
  const viewsOfParts = new Set(views.map(view => view.part)).size > 1;
  const coverageOfParts = coverage.length > 1;
  // A related annotation picked from another's values: the whole list, for the selection it makes.
  const selectRelated = (entry) => { setShowAllFor(selectionKeyOf(entry.featureIds)); pmi.select(entry.key); };
  // A kind asked for from a face's menu: its form, the section open on it.
  const stack = useContext(ToolStackContext);
  useEffect(() => {
    if (!request) return;
    const option = options.find(item => item.kind === request.kind && item.available);
    if (option) begin(option);
    stack?.open?.("pmi");
    // Once per request: the options follow the pick, which the request has just made.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.key]);
  const closeDraft = () => { setDraft(null); onRequestDone?.(); };
  const shownCount = pmi.entries.filter(drawnKind).length;
  return <ToolPanel id="pmi" title="PMI" label="PMI" icon={PmiIcon} fit="tree" resizable collapsible={false}>
    <ToolPanelHeadAction>
      {pmi.editable ? <DropdownMenu modal={false}>
        <TooltipHint content={t("pmi.new")} side="bottom">
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label={t("pmi.new")} data-pmi-new-menu="" className={TOOL_PANEL_BUTTON_CLASS}><Plus className="size-3" aria-hidden="true" /></button>
          </DropdownMenuTrigger>
        </TooltipHint>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel className="text-muted-foreground">{t("pmi.onFacesPicked")}</DropdownMenuLabel>
          {options.map(option => <Fragment key={option.kind}>
            {option.kind === FIRST_OF_PART ? <DropdownMenuSeparator /> : null}
            <DropdownMenuItem disabled={!option.available} data-pmi-new-kind={option.kind} onSelect={() => begin(option)}>
              <PmiGlyph name={optionGlyph(option.kind)} className="size-3.5" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate">{option.label}</span>
              {!option.available ? <span className="truncate text-micro text-muted-foreground">{option.need}</span> : null}
            </DropdownMenuItem>
          </Fragment>)}
        </DropdownMenuContent>
      </DropdownMenu> : null}
      {shownCount ? <TooltipHint content={t(pmi.off ? "pmi.revealAll" : "pmi.hideAll")} side="bottom">
        <button type="button" aria-label={t(pmi.off ? "pmi.revealAll" : "pmi.hideAll")} aria-pressed={pmi.off} data-pmi-visibility-all=""
          className={TOOL_PANEL_BUTTON_CLASS} onClick={() => pmi.setOff(!pmi.off)}>
          {pmi.off ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
        </button>
      </TooltipHint> : null}
    </ToolPanelHeadAction>
    {draft?.call ? <NewEntry key={draft.started} option={draft}
      onCancel={closeDraft} onAdd={(call) => { pmi.add(draft.part, call); closeDraft(); }} /> : null}
    {moving ? <FileSheetStatusText className="py-1">{t("pmi.moving")}</FileSheetStatusText> : null}
    {!pmi.entries.length && !views.length && !draft ? <FileSheetStatusText className="py-1">{t("pmi.empty")}</FileSheetStatusText> : null}
    <div data-pmi-groups="">
      {views.length ? <FileSheetSettingsSection title={t("pmi.views")} sectionId="pmi-views">
        <ul className="px-1 text-tiny" aria-label={t("pmi.views")}>{views.map(view => <ViewRow key={view.key} view={view} pmi={pmi} ofParts={viewsOfParts} />)}</ul>
      </FileSheetSettingsSection> : null}
      {notes.length ? <FileSheetSettingsSection title={t("pmi.notes")} sectionId="pmi-notes">
        <ul className={cn("px-1 text-tiny", pmi.off && "opacity-60")} aria-label={t("pmi.notes")}>
          {notes.map((entry) => {
            const { number, text } = entry.callout;
            return <EntryRow key={entry.key} entry={entry} pmi={pmi} label={t("pmi.noteLabel", { number, text })} rowProps={{ "data-pmi-note": entry.id }} onSelectRelated={selectRelated}>
              <TooltipHint content={text} overflowOnly><span className="min-w-0 flex-1 truncate">{`${number}. ${text}`}</span></TooltipHint>
              {notesOfParts ? <TreeRowLabel className="shrink-0 text-micro text-muted-foreground">{entry.partName}</TreeRowLabel> : null}
            </EntryRow>;
          })}
        </ul>
      </FileSheetSettingsSection> : null}
      {coverage.length ? <FileSheetSettingsSection title={t("pmi.coverage")} sectionId="pmi-coverage" switchLabel={t("pmi.showUncovered")}
        enabled={Boolean(pmi.uncoveredShown)} onEnabledChange={shown => pmi.showUncovered(shown)}>
        {coverage.map(item => <div key={item.part ?? "none"} className="px-2" data-pmi-coverage={item.part ?? ""}>
          <FileSheetStatusText className="px-0 py-0.5">{`${coverageOfParts && item.partName ? `${item.partName}: ` : ""}${uncoveredText(item.uncovered.length, t)}`}</FileSheetStatusText>
          {item.conflicts.map(conflict => <Warning key={`${conflict.kind}:${conflict.ids.join(",")}`} data-pmi-conflict={conflict.kind}>
            {`${conflict.ids.join(", ")}: ${conflict.problem}`}</Warning>)}
          {item.suggestions.map(said => <TooltipHint key={`${said.kind}:${said.faces.join(",")}`} content={said.why}>
            <div className="py-0.5 text-tiny" data-pmi-suggestion={said.kind}>
              <div>{said.question}</div>
              <code className="block break-words font-mono text-micro text-muted-foreground">{said.answer}</code>
            </div>
          </TooltipHint>)}
        </div>)}
      </FileSheetSettingsSection> : null}
      {annotations.length ? <FileSheetSettingsSection title={t("pmi.annotations")} sectionId="pmi-annotations">
        {featureIds.length ? <div className="flex flex-wrap items-center justify-between gap-1 border-b border-border/60 px-2 py-1 text-tiny">
          <span className="text-muted-foreground">{filtered ? t(visible.length === 1 ? "pmi.forSelectionOne" : "pmi.forSelectionMany", { count: visible.length }) : t("pmi.allPmi")}</span>
          <Button type="button" variant="ghost" size="xs" className="h-6 text-tiny" onClick={() => setShowAllFor(filtered ? selectionKey : "")}>{t(filtered ? "pmi.showAllPmi" : "pmi.forSelection")}</Button>
        </div> : null}
        {filtered && !visible.length ? <FileSheetStatusText className="py-1">{t("pmi.noneForSelection")}</FileSheetStatusText> : null}
        <ul className={cn("px-1 text-tiny", pmi.off && "opacity-60")} aria-label="PMI" data-pmi-rows="">
          {visible.map(entry => <EntryRow key={entry.key} entry={entry} pmi={pmi} label={entry.callout.text} rowProps={{ "data-pmi-row": entry.id }} onSelectRelated={selectRelated}>
            <TreeRowLabel className="min-w-0 shrink tabular-nums">{entry.supported ? entry.callout.text : entry.label || entry.id}</TreeRowLabel>
            {/* Its id, where it says more than the callout (a datum's id is its letter). */}
            <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{!entry.supported ? t("pmi.notShown") : entry.kind === "datum" ? "" : entry.id}</TreeRowLabel>
          </EntryRow>)}
        </ul>
      </FileSheetSettingsSection> : null}
    </div>
  </ToolPanel>;
}
