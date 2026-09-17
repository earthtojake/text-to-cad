// The Materials editor's own chunk. Reached only through the Render-mode
// Materials tab, so it is imported lazily by MaterialsSettingsTab.js and costs
// nothing on an Inspect-only load.
import { useEffect, useMemo, useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import {
  applyMaterialChoice,
  materialForSelection,
  sourceMaterialOverlayIsEmpty,
  MATERIAL_FINISH_PRESETS,
  duplicateSourceMaterialOverlay,
  effectiveSourceAppearance,
  patchSourceMaterialOverlay,
  sourceMaterialFallbackColor,
  sourceMaterialEditorValue
} from "../../workbench/sourceMaterialSession.js";
import { Button } from "@hardcore/ui/primitives/button";
import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  parseFileSheetNumberInput
} from "./FileSheet.js";

function clampUnit(value) {
  return Math.min(Math.max(Number(value) || 0, 0), 1);
}

function MaterialSlider({ label, value, onChange }) {
  const numericValue = clampUnit(value);
  return (
    <FileSheetSliderField
      label={label}
      value={numericValue.toFixed(2)}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, {
        fallback: numericValue,
        min: 0,
        max: 1
      }))}
      valueInputProps={{ ariaLabel: `${label} value` }}
    >
      <Slider
        value={[numericValue]}
        min={0}
        max={1}
        step={0.01}
        onValueChange={(next) => onChange(clampUnit(next[0]))}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        aria-label={label}
      />
    </FileSheetSliderField>
  );
}

// Undo, the overlay and the selection all belong to the workspace's material
// session hook: this panel unmounts whenever the Studio tab is shown, and
// anything it kept for itself would not survive that.
export default function MaterialsSettingsContent({ appearance, overlay, undo = null, targets = [], selectedPartIds = [],
  onSelectParts, onOverlayChange, onUndo, onReset, scope = "" }) {
  const effective = useMemo(() => effectiveSourceAppearance(appearance, overlay), [appearance, overlay]);
  const parts = targets.filter(target => !target.group);
  const selected = parts.filter(part => selectedPartIds.includes(part.occurrenceIds[0]));
  const ids = selected.map(part => part.occurrenceIds[0]);
  const current = materialForSelection(effective, ids);
  const material = effective?.materials?.[current.materialId];
  const usage = Object.values(effective?.assignments || {}).filter(id => id === current.materialId).length;
  const selectionKey = JSON.stringify([scope, ids, current.materialId]);
  const [editingFinish, setEditingFinish] = useState(false);
  const update = (next) => onOverlayChange?.(next);
  const apply = (choice) => {
    const result = applyMaterialChoice(appearance, overlay, ids, choice);
    if (result) update(result.overlay);
  };
  const [editingShared, setEditingShared] = useState(false);
  useEffect(() => { setEditingFinish(false); setEditingShared(false); }, [selectionKey]);
  const title = selected.length === 1 ? selected[0].label : `${selected.length} parts`;
  const fallbackColor = sourceMaterialFallbackColor(effective, current.materialId, parts.map(part => ({ id: part.occurrenceIds[0], color: part.color })));
  const sharedOutsideSelection = material && usage > ids.length;
  const editable = material && (!sharedOutsideSelection || editingShared);
  const change = (key, value) => update(patchSourceMaterialOverlay(overlay, current.materialId, { [key]: value }));
  const swatch = (materialId, partColor) => <span aria-hidden="true" className="size-4 shrink-0 rounded-full border border-border"
    style={{ backgroundColor: sourceMaterialEditorValue(effective?.materials?.[materialId], "baseColor",
      partColor || sourceMaterialFallbackColor(effective, materialId, parts.map(part => ({ id: part.occurrenceIds[0], color: part.color })))) }} />;
  const partList = (list) => <div className="max-h-40 overflow-y-auto px-2 pb-1">
    {list.map(part => {
      const id = part.occurrenceIds[0];
      const assignedId = effective?.assignments?.[id];
      return <button key={id} type="button" aria-pressed={ids.includes(id)}
        onClick={event => onSelectParts?.(event.shiftKey ? ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id] : [id])}
        className={cn("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11px] hover:bg-accent/60", ids.includes(id) && "bg-accent")}>
        {swatch(assignedId, part.color)}<span className="min-w-0 flex-1 break-words">{part.label}</span>
        <span className="text-muted-foreground">{effective?.materials?.[assignedId]?.name || "Unassigned"}</span>
        {ids.includes(id) ? <Check aria-hidden="true" className="size-3 shrink-0" /> : null}
      </button>;
    })}
  </div>;
  const optionList = (label, options) => <FileSheetSubsection title={label}>
    <div className="grid grid-cols-2 gap-1 px-2" aria-label={label}>
      {options.map(option => <div key={option.value} className="relative flex rounded border border-border/60">
        <button type="button" disabled={!ids.length} aria-pressed={current.materialId && option.value === `material:${current.materialId}` || false}
          onClick={() => apply(option.value)}
          className={cn("flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded px-2 text-left text-[11px] hover:bg-accent/60 disabled:opacity-50",
            option.value === `material:${current.materialId}` && "bg-accent ring-1 ring-primary")}>
          {option.materialId ? swatch(option.materialId) : null}
          <span className="break-words">{option.label}</span>
          {option.value === `material:${current.materialId}` ? <Check aria-hidden="true" className="size-3 shrink-0" /> : null}
        </button>
        {option.materialId ? <details className="relative">
          <summary aria-label={`Options for ${option.label}`} className="cursor-pointer list-none px-2 py-2 text-muted-foreground">⋯</summary>
          <div className="absolute right-0 top-full z-10 w-44 rounded border bg-popover p-1 shadow-md">
            <button type="button" className="w-full rounded px-2 py-2 text-left text-[11px] hover:bg-accent"
              disabled={!parts.some(part => effective?.assignments?.[part.occurrenceIds[0]] === option.materialId)}
              onClick={event => {
                onSelectParts?.(parts.filter(part => effective?.assignments?.[part.occurrenceIds[0]] === option.materialId).map(part => part.occurrenceIds[0]));
                event.currentTarget.closest("details").open = false;
              }}>Select parts using {option.label}</button>
          </div>
        </details> : null}
      </div>)}
    </div>
  </FileSheetSubsection>;
  return <div className="py-2" data-cad-materials-settings-section="true">
    <FileSheetSubsection title="Parts">
      <FileSheetStatusText>{ids.length ? `Selected: ${title} · ${current.label}` : "Select a part below or in the model. Shift-click for multiple."}</FileSheetStatusText>
      {partList(parts)}
      <FileSheetButtonRow columns={ids.length ? 2 : 1}>
        <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} disabled={!parts.length}
          onClick={() => onSelectParts?.(parts.map(part => part.occurrenceIds[0]))}>Select all parts</Button>
        {ids.length ? <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => onSelectParts?.([])}>Clear selection</Button> : null}
      </FileSheetButtonRow>
    </FileSheetSubsection>
    {optionList("In this model", Object.entries(effective?.materials || {}).map(([id, entry]) => ({ value: `material:${id}`, label: entry.name, materialId: id })))}
    {optionList("Presets", MATERIAL_FINISH_PRESETS.map(preset => ({value: `preset:${preset.id}`, label: preset.name})))}
    <FileSheetStatusText>{ids.length ? "Click a material to apply it." : "Select a part to change its material."}</FileSheetStatusText>
    {undo ? <FileSheetButtonRow columns={1}><Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
      onClick={() => onUndo?.()}><RotateCcw className="size-3.5" />Undo</Button></FileSheetButtonRow> : null}
    {ids.length && material ? <FileSheetButtonRow columns={1}><Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
      aria-expanded={editingFinish} onClick={() => setEditingFinish(value => !value)}>{editingFinish ? "Close advanced settings" : "Advanced settings…"}</Button></FileSheetButtonRow> : null}
      {ids.length && material && editingFinish ? <FileSheetSubsection title={`Edit ${material.name}`}>
        {sharedOutsideSelection ? <>
          <FileSheetStatusText>Shared by {usage} parts. Editing this material changes all of them.</FileSheetStatusText>
          <FileSheetButtonRow columns={1}>
            <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => setEditingShared(value => !value)}>{editingShared ? "Stop editing shared material" : "Edit shared material"}</Button>
            <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => {
              const result = duplicateSourceMaterialOverlay(appearance, overlay, current.materialId, ids);
              if (result?.overlay) update(result.overlay);
            }}>Make unique for selection</Button>
          </FileSheetButtonRow>
        </> : null}
        {editable ? <>
          <FileSheetColorRow label="Base color" value={sourceMaterialEditorValue(material, "baseColor", fallbackColor)} onChange={value => change("baseColor", value)} />
          {[ ["Roughness", "roughness"], ["Metalness", "metalness"], ["Clearcoat", "clearcoat"], ["Coat roughness", "clearcoatRoughness"], ["Opacity", "opacity"] ].map(([label, key]) =>
            <MaterialSlider key={key} label={label} value={sourceMaterialEditorValue(material, key)} onChange={value => change(key, value)} />)}
        </> : null}
      </FileSheetSubsection> : null}
    <FileSheetStatusText>Edits are remembered in this browser tab. Source files are unchanged.</FileSheetStatusText>
    <FileSheetButtonRow columns={1}><Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
      disabled={sourceMaterialOverlayIsEmpty(overlay)} onClick={() => onReset?.()}><RotateCcw className="size-3.5" />Reset authored</Button></FileSheetButtonRow>
  </div>;
}
