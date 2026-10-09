import { useState } from "react";
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { cn } from "@text-to-cad/ui/utils";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { TREE_INDENT_PX, TreeRowChevron, TreeRowGuides, TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetFieldGrid, FileSheetSelectRow, FileSheetSliderField, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";
import ToolPanel, { ToolPanelClose, ToolPanelFooterButton } from "../kit/tools/ToolPanel.jsx";
import { deformationRange, formatValue } from "./feaResult.js";

// The fields in plain words, short enough for the panel's one width; the file's own names (von
// Mises stress) are the colour bar's.
const FIELD_WORDS = Object.freeze({ _von_mises: "Stress", _displacement: "Displacement" });

/**
 * Which field the colours show and how much larger than life the displacement is drawn: Study's
 * Result. The file carries every field and the true displacement (feaResult.js), so both are
 * choices, not readouts. `field` and `scale` arrive resolved.
 */
function FeaResultControls({ result, field, scale, onFieldChange, onScaleChange }) {
  const range = deformationRange(result.deformationScale);
  return (
    <>
      <FileSheetFieldGrid columns={1}>
        <FileSheetSelectRow
          hideLabel
          className="px-0"
          label="Field"
          ariaLabel="Result field"
          value={field.attribute}
          onValueChange={onFieldChange}
          options={result.fields.map((entry) => ({ value: entry.attribute, label: FIELD_WORDS[entry.attribute] || entry.name }))}
        />
      </FileSheetFieldGrid>
      <FileSheetSliderField
        label="Deformation"
        labelTitle="How much larger than life the displacement is drawn"
        value={`×${formatValue(scale)}`}
        onValueCommit={(draft) => onScaleChange(parseFileSheetNumberInput(String(draft).replace(/^×/, ""), {
          fallback: scale, min: range.min, max: range.max
        }))}
        valueInputProps={{ ariaLabel: "Deformation scale value" }}
      >
        <Slider
          className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
          value={[scale]}
          min={range.min}
          max={range.max}
          step={range.step}
          aria-label="Deformation scale"
          thumbProps={{ "aria-label": "Deformation scale" }}
          onValueChange={(next) => onScaleChange(clamp(next[0], range.min, range.max))}
        />
      </FileSheetSliderField>
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

/** Text that wraps between words alone: a hyphenated name ("6061-T6") and a number and its unit ("276 MPa") never part. */
const unbroken = (text) => String(text).replace(/(\S)-(?=\S)/g, "$1\u2011").replace(/(\d) (?=[A-Za-zµ°%])/g, "$1\u00a0");

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
 * One of Study's rows, the Links tree's: a 16px disclosure column, then its name and detail. A row
 * that stands for faces (a fixed face, a load, a load's face) or for parts (an assembly's part or
 * joint) is a button that chooses them; a group (Parts, Connections, Fixed, Loads, Result) only
 * opens and closes. `content`: what an open row shows in place
 * of child rows (Result's controls).
 */
function StudyRow({ row, depth, chosen, collapsed, toggle, onChoose, content = null }) {
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
        className="grid h-6 w-4 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => toggle(row.id)}><TreeRowChevron expanded={open} /></button> : <span className="w-4 shrink-0" />}
      {choosable ? <button type="button" aria-label={`Select ${row.label}`} aria-pressed={active} onClick={() => onChoose(row)}
        className={cn("flex min-w-0 flex-1 gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          row.wrap ? "flex-wrap items-baseline py-1" : "h-full items-center")}>
        {row.wrap ? <WrappedRowText row={row} /> : <RowText row={row} />}
      </button> : <span className="flex h-full min-w-0 flex-1 items-center gap-1.5 pr-2"><RowText row={row} /></span>}
    </TreeRowSurface>
    {open && row.children ? <ul>{row.children.map((child) => <StudyRow key={child.id} row={child} depth={depth + 1}
      {...{ chosen, collapsed, toggle, onChoose }} />)}</ul> : null}
    {open && content ? <div className="pb-1 pl-4" data-study-result="">{content}</div> : null}
  </li>;
}

const RESULT_ROW = Object.freeze({ id: "result", label: "Result", detail: "" });

/**
 * An FEA result's Select panel, **Study**, closable like the Features tree (`tree`), and the
 * **Reference** for a face picked on the result. Study reads the result's study as the tree's rows
 * (`studyRows`: an assembly's parts and connections, material, fixed faces, loads with their faces, mesh), then Result: the field and
 * deformation. A result written before its study was recorded has Result alone. Choosing a row
 * that stands for faces is `onChoose(row)`; `chosen` is the row (or picked face) chosen.
 *
 * @param {{ active: boolean, result: object, rows: object[], chosen: string, onChoose(row: object): void,
 *   field: object, scale: number, onFieldChange(attribute: string): void, onScaleChange(scale: number): void,
 *   reference: { title: string, ref: string, role: string } | null, onClearSelection(): void,
 *   copy: { label: string, shortcut: string, onCopy(): unknown } | null }} props
 */
export default function FeaStudyPanel({ active, result, rows, chosen, onChoose, field, scale, onFieldChange, onScaleChange,
  reference, onClearSelection, copy }) {
  const [collapsed, setCollapsed] = useState(() => new Set());
  const toggle = (id) => setCollapsed((current) => {
    const next = new Set(current);
    if (!next.delete(id)) next.add(id);
    return next;
  });
  const shared = { depth: 0, chosen, collapsed, toggle, onChoose };
  return <>
    {/* Headed "Study"; its X closes it, and Select, pressed while it is the tool, opens it again. */}
    <ToolPanel id="tree" title="Study" label="Study" actions={<ToolPanelClose />} fit="tree" resizable fitContent closable collapsible={false} hidden={!active}>
      <ul className="flex flex-col px-1 pb-1 text-tiny" aria-label="Study">
        {rows.map((row) => <StudyRow key={row.id} row={row} {...shared} />)}
        <StudyRow row={RESULT_ROW} {...shared} content={<FeaResultControls result={result} field={field} scale={scale}
          onFieldChange={onFieldChange} onScaleChange={onScaleChange} />} />
      </ul>
    </ToolPanel>
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
