import { useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { useI18n } from "@text-to-cad/ui/i18n";
import { TREE_INDENT_PX, TreeRowChevron, TreeRowGuides, TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Checkbox } from "@text-to-cad/ui/primitives/checkbox";
import { InfoRow } from "../kit/inspector/referenceRows.jsx";
import { controlRow } from "./fea/controlRow.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { formatValue } from "./feaResult.js";
import FeaVerdict from "./FeaVerdict.jsx";
import { STUDY_GLYPHS } from "./feaGlyphs.jsx";

/** A multiple on its slider's steps, to the step: the Load's 0.1 as "0.5", a deformation's 0.5 as "12.0", its 1 as
 * "6000"; one typed between them keeps its own figures ("0.55"), never shown as a value it is not. */
const stepped = (value, step) => {
  const v = Number(value) || 0;
  if (!(step > 0) || Math.abs(v / step - Math.round(v / step)) > 1e-6) return formatValue(v);
  return v.toFixed(step >= 1 ? 0 : Math.ceil(-Math.log10(step) - 1e-9));
};

/** A control's number as its value field shows it: a multiple to its step ("×12.0", "×0.5"), others with their unit after ("138 MPa"). */
const controlText = (value, control) => (control.unit === "×" ? `×${stepped(value, control.step)}`
  : `${formatValue(value)}${control.unit ? ` ${control.unit}` : ""}`);

/**
 * Study's What you see: the field, the deformation and the load (`feaControls`), each a settings row
 * (`controlRow`). The file carries every field and the true displacement (feaResult.js), so each is a
 * choice, not a readout. `values` by control id. `markers`: whether the model shows where the study
 * holds and loads it (its title, "Loads and fixtures"; `text`, what it draws), a checkbox after the controls.
 */
function FeaResultControls({ controls, values, onChange, markers = null }) {
  const { t } = useI18n();
  // One value box width for every number, the widest any of them shows, so their sliders end together.
  const boxTexts = controls.filter((control) => control.type === "number")
    .flatMap((control) => [values[control.id], control.min, control.max].map((value) => controlText(value, control)));
  return (
    // A select gives way before its label in the narrow panel ("Displacement" would squeeze "Show" away).
    <div className="flex flex-col gap-1.5 [&_span:has(+span>[data-slot=select-trigger])]:shrink-0 [&_span:has(>[data-slot=select-trigger])]:min-w-0 [&_span:has(>[data-slot=select-trigger])]:shrink [&_[data-slot=select-trigger]]:min-w-0 [&_[data-slot=select-trigger]]:max-w-full">
      {controls.map((control) => controlRow({
        control, value: values[control.id], valueText: controlText, t, boxTexts,
        onChange: (value) => onChange(control.id, value),
      }))}
      {markers ? <div className="flex min-w-0 items-center gap-2 px-2 text-tiny" data-fea-markers="">
        <Checkbox checked={markers.on} onCheckedChange={(on) => markers.onChange(on === true)} aria-label={markers.title} />
        <span className="shrink-0" aria-hidden="true">{markers.title}</span>
        <TooltipHint content={markers.text} overflowOnly><span className="min-w-0 truncate text-micro text-muted-foreground">{markers.text}</span></TooltipHint>
      </div> : null}
    </div>
  );
}

/**
 * A row's name, then what it says in muted text: in a narrow panel the detail takes the truncation,
 * then the name ("display base rounded countersunk · face 9"), hinted whole when cut off.
 */
function RowText({ row }) {
  return <>
    <TreeRowLabel className={row.detail ? "max-w-full shrink-0" : "flex-1"}>{row.label}</TreeRowLabel>
    {row.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{row.detail}</TreeRowLabel> : null}
  </>;
}

/** Text that wraps between words alone: a hyphenated name ("6061-T6"), a number and its unit ("276 MPa") and "holds 1.4×" never part. */
const unbroken = (text) => String(text).replace(/(\S)-(?=\S)/g, "$1\u2011").replace(/(\d) (?=[A-Za-zµ°%])/g, "$1\u00a0")
  .replace(/\bholds (?=\d)/g, "holds\u00a0");

/** A row's name and detail that wrap between words (a long part name, a detail that will not fit the line) instead of being cut off. */
function WrappedRowText({ row }) {
  return <>
    <span className="min-w-0 [overflow-wrap:anywhere]">{row.label}</span>
    {row.detail ? <span className="min-w-0 text-micro text-muted-foreground [overflow-wrap:break-word]" data-study-detail="">{unbroken(row.detail)}</span> : null}
  </>;
}

/**
 * A row that only says something (the material's name, the mesh): its label then any detail ("Mesh
 * 3.7 mm elements"), on one line where both fit, else the detail whole on the line under the label,
 * never broken between words. Its further words are its hint ("refined from 6 mm", each part's
 * material); a row cut off even on its own line is hinted whole.
 */
function StudyFactRow({ row, depth }) {
  const hint = row.hint || [row.label, row.detail].filter(Boolean).join(" ");
  return <li className="min-w-0">
    <TreeRowSurface dense className="h-auto min-h-6 gap-0 pr-0 hover:bg-transparent" style={{ height: "auto", paddingLeft: depth * TREE_INDENT_PX }} data-study-row={row.id}>
      <TreeRowGuides depth={depth} column={16} />
      <span className="w-4 shrink-0" />
      <TooltipHint content={hint} overflowOnly={!row.hint}>
        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5 py-1 pr-2">
          <span className={cn("min-w-0 max-w-full", row.wrap ? "[overflow-wrap:break-word]" : "truncate")}>{row.wrap ? unbroken(row.label) : row.label}</span>
          {row.detail ? <span className="min-w-0 max-w-full truncate text-micro text-muted-foreground" data-study-detail="">{row.detail}</span> : null}
        </span>
      </TooltipHint>
    </TreeRowSurface>
  </li>;
}

/**
 * A heading of the study's setup, read as the start of a sentence ("Held at", "Pushed", "Made of"):
 * the glyph its marker is drawn as on the model in the disclosure column, its words muted, and its
 * rows always under it, hung from a line under the glyph. Not a control: it neither chooses nor folds.
 */
function StudyHeadingRow({ row, depth, ...rest }) {
  const Glyph = STUDY_GLYPHS[row.glyph];
  // A little air above each heading after the first, so the setup reads as separate sentences.
  return <li className="min-w-0 [&:not(:first-child)]:pt-1">
    <div className="relative flex h-6 min-w-0 items-center text-tiny text-muted-foreground" style={{ paddingLeft: depth * TREE_INDENT_PX }} data-study-row={row.id} data-study-heading="">
      <span className="grid w-4 shrink-0 place-items-center">{Glyph ? <Glyph /> : null}</span>
      <span className="min-w-0 truncate pl-1.5">{row.label}</span>
    </div>
    <ul>{row.children.map((child) => <StudyRow key={child.id} row={child} depth={depth + 1} {...rest} />)}</ul>
  </li>;
}

/**
 * One of a tree's rows (Parts', Study's), the Links tree's: a 16px disclosure column, then its name
 * and detail. A row that stands for faces (a fixed face, a load, a load's face) or for parts (an
 * assembly's part or joint) is a button that chooses them; a group (What you see, Details) only opens
 * and closes, and a heading of the setup (Held at, Pushed, Made of) does neither (`StudyHeadingRow`). `contents`: what an open row shows in place of child rows, by id (What you see's controls).
 */
function StudyRow({ row, depth, chosen, collapsed, toggle, onChoose, contents }) {
  const { t } = useI18n();
  const content = contents[row.id] || null;
  const choosable = Boolean(row.faces || row.refs);
  if (row.glyph && row.children?.length) return <StudyHeadingRow {...{ row, depth, chosen, collapsed, toggle, onChoose, contents }} />;
  if (!choosable && !row.children && !content) return <StudyFactRow row={row} depth={depth} />;
  const branch = Boolean(row.children?.length || content);
  const open = branch && !collapsed.has(row.id);
  const active = chosen === row.id;
  return <li className={cn("min-w-0", depth === 0 && "[&:not(:first-child)]:pt-1")}>
    <TreeRowSurface dense active={active} className={cn("gap-0 pr-0", row.wrap && "h-auto min-h-6")}
      style={{ paddingLeft: depth * TREE_INDENT_PX, ...(row.wrap ? { height: "auto" } : {}) }} data-study-row={row.id}>
      <TreeRowGuides depth={depth} column={16} />
      {branch ? <button type="button" aria-label={t(open ? "tree.collapse" : "tree.expand", { name: row.label })} aria-expanded={open}
        className="grid h-6 w-4 shrink-0 place-items-center self-start rounded focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => toggle(row.id)}><TreeRowChevron expanded={open} /></button> : <span className="w-4 shrink-0" />}
      {choosable ? <TooltipHint content={row.hint || (row.wrap ? null : [row.label, row.detail].filter(Boolean).join(" "))} overflowOnly={!row.hint}>
        <button type="button" aria-label={t("tree.select", { name: row.name || row.label })} aria-pressed={active} onClick={() => onChoose(row)}
          className={cn("flex min-w-0 flex-1 gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            row.wrap ? "flex-wrap items-baseline py-1" : "h-full items-center")}>
          {row.wrap ? <WrappedRowText row={row} /> : <RowText row={row} />}
        </button>
      </TooltipHint> : <span className="flex h-full min-w-0 flex-1 items-center gap-1.5 pr-2"><RowText row={row} /></span>}
    </TreeRowSurface>
    {open && row.children ? <ul>{row.children.map((child) => <StudyRow key={child.id} row={child} depth={depth + 1}
      {...{ chosen, collapsed, toggle, onChoose, contents }} />)}</ul> : null}
    {open && content ? <div className="pb-1 pl-4" data-study-result="">{content}</div> : null}
  </li>;
}

/**
 * One section of the file sidebar, headed by its title: Parts or Study, its rows in the sidebar's one scroll.
 * `startsCollapsed`: the rows it opens with shut (every part but the weakest). Which rows are open is the
 * section's own, kept while it is mounted (open in the sidebar or not).
 */
function StudyTreePanel({ id, title, blocks, startsCollapsed, fit, chosen, onChoose, contents }) {
  const [collapsed, setCollapsed] = useState(() => new Set(startsCollapsed));
  const toggle = (rowId) => setCollapsed((current) => {
    const next = new Set(current);
    if (!next.delete(rowId)) next.add(rowId);
    return next;
  });
  return <ToolPanel id={id} title={title} label={title} fit={fit} collapsible={false}>
    {blocks.map((block, index) => (block.rows
      ? <ul key={index} className="flex flex-col px-1 pb-1 text-tiny" aria-label={title}>
        {block.rows.map((row) => <StudyRow key={row.id} row={row} depth={0} {...{ chosen, collapsed, toggle, onChoose, contents }} />)}
      </ul>
      : <div key={index} className={index ? "pt-1" : undefined}>{block.element}</div>))}
  </ToolPanel>;
}

// What the view shows and how: its controls, under the setup and above Details.
const RESULT_ROW = Object.freeze({ id: "result", label: "What you see", key: "fea.whatYouSee", detail: "" });
const NONE = Object.freeze([]);

/** The ids of the rows that open shut (`collapsed`: a load's faces), at any depth. */
const collapsedIds = (rows) => rows.flatMap((row) => [...(row.collapsed ? [row.id] : []), ...collapsedIds(row.children || NONE)]);

// The sidebar sections' ids, under which the person's size for each is kept.
export const FEA_PARTS_PANEL_ID = "parts";
export const FEA_STUDY_PANEL_ID = "study";

/**
 * An FEA result's sections of the file sidebar, whatever the tool, composed from what the file holds:
 * **Parts** only for an assembly whose panel shows (`parts`: `partRows`, each part with its joints under it,
 * the weakest part open; `feaShowsParts`, from six parts up), then **Study**: the verdict at the load shown
 * (`verdict`: `feaVerdict`, none where the file cannot say) over one list of the setup (`setup`,
 * `studySections`: where it is held, what pushes it, what it is made of, each only where the file records it),
 * What you see: the field, deformation and load controls and the markers' gate (`result`: `FeaResultControls`'
 * props), and Details (`details`), shut. Choosing a row that stands for faces or parts is `onChoose(row)`;
 * `chosen` is the row (or picked face) chosen. A face picked on the result is Quick Edit's chip, its card
 * `FaceCard`.
 *
 * @param {{ parts?: object[], openPart?: number, setup: object[], details: object[],
 *   verdict?: object | null, chosen: string, onChoose(row: object): void,
 *   result: { controls: object[], values: Record<string, unknown>, onChange(id: string, value: unknown): void,
 *     markers?: { title: string, text: string, on: boolean, onChange(on: boolean): void } | null } }} props
 */
export default function FeaStudyPanel({ parts = NONE, openPart = -1, setup, details, verdict = null, chosen, onChoose, result }) {
  const { t } = useI18n();
  const contents = {
    [RESULT_ROW.id]: <FeaResultControls {...result} />,
  };
  const blocks = [
    ...(verdict ? [{ element: <FeaVerdict verdict={verdict} chosen={chosen} onChoose={onChoose} /> }] : NONE),
    { rows: [...setup, { ...RESULT_ROW, label: t(RESULT_ROW.key) }, ...details] },
  ];
  const panels = [
    parts.length ? { id: FEA_PARTS_PANEL_ID, title: t("fea.parts"), blocks: [{ rows: parts }], startsCollapsed: parts.filter((_, index) => index !== openPart).map((row) => row.id), fit: "tree" } : null,
    { id: FEA_STUDY_PANEL_ID, title: t("fea.study"), startsCollapsed: collapsedIds([...setup, ...details]), fit: "tree", blocks },
  ].filter(Boolean);
  return <>{panels.map((panel) => <StudyTreePanel key={panel.id} {...panel} chosen={chosen} onChoose={onChoose} contents={contents} />)}</>;
}

/** A face picked on the result, as its Quick Edit chip's card under the ref the chip names: what the study does to it, and its part. */
export function FaceCard({ face }) {
  const { t } = useI18n();
  return <>
    <InfoRow label={t("fea.study")}>{face.role}</InfoRow>
    {face.part ? <InfoRow label={t("fea.part")}>{unbroken(face.part)}</InfoRow> : null}
  </>;
}
