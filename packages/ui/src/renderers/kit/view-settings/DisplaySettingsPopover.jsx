import { cloneElement, isValidElement, useState, useEffect, useRef } from "react";
import { Slider } from "@hardcore/ui/primitives/slider";
import { Popover, PopoverContent, PopoverTrigger } from "@hardcore/ui/primitives/popover";
import { ToolbarButton } from "../tools/ToolbarButton.js";
import { RenderModeIcon } from "./DisplayModeOptions.js";
import FilePanelSections from "../inspector/FilePanelSections.jsx";
import { FileSheetSliderField, FILE_SHEET_PRECISION_SLIDER_CLASSES, parseFileSheetNumberInput } from "../inspector/FileSheet.js";
import { MAX_ORBIT_SPEED } from "../tools/fullscreen/orbitPreferences.js";

/** A properties sheet for the Display tool. Dismissing the sheet keeps the tool selected. */
export default function DisplaySettingsPopover({ settings, actions, active, onActivate, preview = false, onPreviewChange, orbitSpeed = 1, onOrbitSpeedChange, container, disabled = false, triggerClassName = "" }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (active === false) setOpen(false); }, [active]);
  const content = useRef(null);
  const nestedDismissals = useRef(new WeakSet());
  const dismissingNestedPopup = useRef(false);
  useEffect(() => {
    if (!open) return;
    const document = container?.ownerDocument ?? window.document;
    // A modal dropdown sends outside clicks through the viewer, which restores
    // viewport focus. Keep that dismissal gesture in the child layer even after
    // it unmounts; Radix may defer the parent outside event until click.
    const capture = event => {
      dismissingNestedPopup.current = !!content.current?.querySelector('[role="combobox"][aria-expanded="true"], [aria-haspopup][aria-expanded="true"]');
      if (dismissingNestedPopup.current) {
        nestedDismissals.current.add(event);
      }
    };
    const finish = () => { dismissingNestedPopup.current = false; };
    document.addEventListener('pointerdown', capture, true);
    document.addEventListener('click', finish);
    document.addEventListener('keydown', finish, true);
    return () => {
      document.removeEventListener('pointerdown', capture, true);
      document.removeEventListener('click', finish);
      document.removeEventListener('keydown', finish, true);
    };
  }, [open, container]);
  const leadingSections = [
    onPreviewChange && { id: "orbit", title: "Orbit", enabled: preview, onEnabledChange: onPreviewChange,
      content: preview ? <FileSheetSliderField compact label="Orbit speed" value={`${Number(orbitSpeed.toFixed(2))}×`}
        onValueCommit={draft => onOrbitSpeedChange?.(parseFileSheetNumberInput(draft, { fallback: orbitSpeed, min: 0, max: MAX_ORBIT_SPEED }))}
        valueInputProps={{ ariaLabel: 'Orbit speed value' }}>
        <Slider thumbProps={{ 'aria-label': 'Orbit speed' }} min={0} max={MAX_ORBIT_SPEED} step={0.05} value={[orbitSpeed]}
          onValueChange={([speed]) => onOrbitSpeedChange?.(speed)} className={FILE_SHEET_PRECISION_SLIDER_CLASSES} />
      </FileSheetSliderField> : null,
    },
  ];
  return <Popover open={open} onOpenChange={next => { if (next) onActivate?.(); setOpen(next); }}>
    <PopoverTrigger asChild>
      <ToolbarButton label="Display" className={triggerClassName} tooltipSide="top" active={active ?? open} aria-pressed={active ?? open} disabled={disabled}>
        <RenderModeIcon className="size-3.5" aria-hidden="true" />
      </ToolbarButton>
    </PopoverTrigger>
    <PopoverContent ref={content}
      onPointerDownOutside={event => {
        if (nestedDismissals.current.has(event.detail.originalEvent)) event.preventDefault();
      }}
      onFocusOutside={event => {
        // Child dismissal can focus the viewport before restoring its trigger.
        if (dismissingNestedPopup.current || event.target === content.current?.ownerDocument.body
          || event.target?.closest?.('[data-slot=select-content]')
          || content.current?.querySelector('[role="combobox"][aria-expanded="true"], [aria-haspopup][aria-expanded="true"]')) event.preventDefault();
      }}
      container={container} align="end" side="bottom" sideOffset={8} collisionPadding={8} aria-label="Display settings"
      collisionBoundary={container} data-cad-display-popover=""
      className="flex w-64 max-w-(--radix-popover-content-available-width) max-h-[min(520px,var(--radix-popover-content-available-height))] flex-col overflow-hidden bg-background p-0 text-tiny data-[state=open]:animate-none data-[state=closed]:animate-none">
      {isValidElement(settings) ? cloneElement(settings, { leadingSections, appearanceControl: actions, sticky: false })
        : <FilePanelSections sections={leadingSections} sticky={false} />}
    </PopoverContent>
  </Popover>;
}
