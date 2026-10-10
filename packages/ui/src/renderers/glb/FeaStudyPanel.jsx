import { useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { TREE_INDENT_PX, TreeRowChevron, TreeRowGuides, TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";
import { KinematicsPoseRow } from "../kit/inspector/kinematicsControls.jsx";
import { parameterRow } from "../kit/inspector/parameterRow.jsx";
import ToolPanel, { ToolPanelClose, ToolPanelFooterButton } from "../kit/tools/ToolPanel.jsx";
import { formatValue } from "./feaResult.js";

/** A control's number as its value field shows it: a multiple as "×12.0", others with their unit after ("138 MPa"). */
const controlText = (value, control) => (control.unit === "×" ? `×${formatValue(value)}` : `${formatValue(value)}${control.unit ? ` ${control.unit}` : ""}`);

/**
 * Study's Result: the controls the study's view chose (`feaControls`), in its order, each a generic
 * parameter row as Position's joints are (`parameterRow`), under a Preset select when the view names
 * presets (Default, each preset, Custom once a control has moved). The file carries every field and
 * the true displacement (feaResult.js), so each is a choice, not a readout. `values` by control id.
 */
function FeaResultControls({ controls, values, presets, preset, onChange, onPreset, onReset }) {
  return (
    <>
      {presets.length ? <KinematicsPoseRow label="Preset" poses={presets} activeValue={preset} onSelect={onPreset} onReset={onReset} /> : null}
      {controls.map((control) => parameterRow({
        parameter: control, value: values[control.id], labelTitle: control.labelTitle, valueText: controlText, step: control.step, wideLabel: control.wideLabel === true,
        onChange: (value) => onChange(control.id, value),
      }))}
    </>
  );
}

/** A row's name, then what it says in muted text: in a narrow panel the detail takes the truncation. */
function RowText({ row }) {
  return <>
    <TreeRowLabel className="max-w-full shrink-0">{row.label}</TreeRowLabel>
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
 * A row that only says something (Material, Mesh): its detail wraps between words onto further
 * lines, as a Reference's values do, so nothing of it is cut off at the panel's one width.
 */
function StudyFactRow({ row }) {
  return <li className="min-w-0">
    <TreeRowSurface dense className="h-auto min-h-6 items-baseline gap-1.5 py-1 pl-4" style={{ height: "auto" }} data-study-row={row.id}>
      <span className="shrink-0">{row.label}</span>
      <span className="min-w-0 flex-1 text-micro text-muted-foreground [overflow-wrap:break-word]" data-study-detail="">{unbroken(row.detail)}</span>
    </TreeRowSurface>
  </li>;
}

/**
 * One of a tree's rows (Parts', Study's), the Links tree's: a 16px disclosure column, then its name
 * and detail. A row that stands for faces (a fixed face, a load, a load's face) or for parts (an
 * assembly's part or joint) is a button that chooses them; a group (Fixed, Loads, Result) only opens
 * and closes. `contents`: what an open row shows in place of child rows, by id (Result's controls).
 */
function StudyRow({ row, depth, chosen, collapsed, toggle, onChoose, contents }) {
  const content = contents[row.id] || null;
  const choosable = Boolean(row.faces || row.refs);
  if (!choosable && !row.children && !content) return <StudyFactRow row={row} />;
  const branch = Boolean(row.children?.length || content);
  const open = branch && !collapsed.has(row.id);
  const active = chosen === row.id;
  return <li className="min-w-0">
    <TreeRowSurface dense active={active} className={cn("gap-0 pr-0", row.wrap && "h-auto min-h-6")}
      style={{ paddingLeft: depth * TREE_INDENT_PX, ...(row.wrap ? { height: "auto" } : {}) }} data-study-row={row.id}>
      <TreeRowGuides depth={depth} column={16} />
      {branch ? <button type="button" aria-label={`${open ? "Collapse" : "Expand"} ${row.label}`} aria-expanded={open}
        className="grid h-6 w-4 shrink-0 place-items-center self-start rounded focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => toggle(row.id)}><TreeRowChevron expanded={open} /></button> : <span className="w-4 shrink-0" />}
      {choosable ? <button type="button" aria-label={`Select ${row.name || row.label}`} aria-pressed={active} onClick={() => onChoose(row)}
        className={cn("flex min-w-0 flex-1 gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          row.wrap ? "flex-wrap items-baseline py-1" : "h-full items-center")}>
        {row.wrap ? <WrappedRowText row={row} /> : <RowText row={row} />}
      </button> : <span className="flex h-full min-w-0 flex-1 items-center gap-1.5 pr-2"><RowText row={row} /></span>}
    </TreeRowSurface>
    {open && row.children ? <ul>{row.children.map((child) => <StudyRow key={child.id} row={child} depth={depth + 1}
      {...{ chosen, collapsed, toggle, onChoose, contents }} />)}</ul> : null}
    {open && content ? <div className="pb-1 pl-4" data-study-result="">{content}</div> : null}
  </li>;
}

/**
 * One closable panel of rows, headed by its title and its X: Parts or Study. `fit`: how it gives way
 * when the stack is short (`ToolPanel`). `startsCollapsed`: the
 * rows it opens with shut (every part but the weakest). Which rows are open is the panel's own, kept
 * while it is mounted (closed or not).
 */
function StudyTreePanel({ id, title, rows, startsCollapsed, fit, hidden, chosen, onChoose, contents }) {
  const [collapsed, setCollapsed] = useState(() => new Set(startsCollapsed));
  const toggle = (rowId) => setCollapsed((current) => {
    const next = new Set(current);
    if (!next.delete(rowId)) next.add(rowId);
    return next;
  });
  return <ToolPanel id={id} title={title} label={title} actions={<ToolPanelClose />} fit={fit} resizable fitContent closable collapsible={false} hidden={hidden}>
    <ul className="flex flex-col px-1 pb-1 text-tiny" aria-label={title}>
      {rows.map((row) => <StudyRow key={row.id} row={row} depth={0} {...{ chosen, collapsed, toggle, onChoose, contents }} />)}
    </ul>
  </ToolPanel>;
}

const RESULT_ROW = Object.freeze({ id: "result", label: "Result", detail: "" });
const NONE = Object.freeze([]);

// The panel ids: Study keeps the tree's, so a single part's is as it always was; Parts is its own.
export const FEA_PARTS_PANEL_ID = "parts";
export const FEA_STUDY_PANEL_ID = "tree";

/**
 * An FEA result's Select panels, each closable as the Features tree is, and the **Reference** for a
 * face picked on the result. They are composed from what the file holds: **Parts** only for an
 * assembly (`parts`: `partRows`, each part with its joints under it, the weakest part open), then
 * **Study** (`rows`: `studyRows`, the material, fixed faces, loads with their faces and mesh, each
 * only where the file records it), ending in Result: the study view's controls (`result`:
 * `FeaResultControls`' props), by default the field and deformation. A result written before its
 * study was recorded has Result alone. Choosing a row that stands for faces or parts is
 * `onChoose(row)`; `chosen` is the row (or picked face) chosen.
 *
 * @param {{ active: boolean, parts?: object[], openPart?: number, rows: object[], chosen: string, onChoose(row: object): void,
 *   result: { controls: object[], values: Record<string, unknown>, presets: object[], preset: string,
 *     onChange(id: string, value: unknown): void, onPreset(value: string): void, onReset(): void },
 *   reference: { title: string, ref: string, role: string } | null, onClearSelection(): void,
 *   copy: { label: string, shortcut: string, onCopy(): unknown } | null }} props
 */
export default function FeaStudyPanel({ active, parts = NONE, openPart = -1, rows, chosen, onChoose, result,
  reference, onClearSelection, copy }) {
  const contents = {
    [RESULT_ROW.id]: <FeaResultControls {...result} />,
  };
  const panels = [
    parts.length ? { id: FEA_PARTS_PANEL_ID, title: "Parts", rows: parts, startsCollapsed: parts.filter((_, index) => index !== openPart).map((row) => row.id), fit: "tree" } : null,
    // Under Parts, Study gives way only after Parts has, as a details panel does, so Result stays in view.
    { id: FEA_STUDY_PANEL_ID, title: "Study", rows: [...rows, RESULT_ROW], startsCollapsed: NONE, fit: parts.length ? "details" : "tree" },
  ].filter(Boolean);
  return <>
    {/* Each headed with its X; Select, pressed while it is the tool, opens the closed ones again. */}
    {panels.map((panel) => <StudyTreePanel key={panel.id} {...panel} hidden={!active} chosen={chosen} onChoose={onChoose} contents={contents} />)}
    {/* The face picked, sized on its own under Study: its ref, what the study does to it, and Copy. */}
    {reference ? <ToolPanel id="reference" title={reference.title} label="Reference details" closeLabel="Clear selection" fit="details" resizable
      collapsible={false} hidden={!active} onClose={onClearSelection}
      footer={copy ? <ToolPanelFooterButton label={copy.label} shortcut={copy.shortcut} onClick={copy.onCopy} /> : null}>
      <div className="px-2 pb-1.5">
        <InfoRow label="Ref"><MonoValue>{reference.ref}</MonoValue></InfoRow>
        <InfoRow label="Study">{reference.role}</InfoRow>
      </div>
    </ToolPanel> : null}
  </>;
}
