import { cloneElement, isValidElement, useState, useEffect, useRef } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@hardcore/ui/primitives/popover";
import { ToolbarButton } from "../tools/ToolbarButton.js";
import { RenderModeIcon } from "./DisplayModeOptions.js";

/** A properties sheet for the Display tool. Closing the sheet releases the tool; settings remain applied. */
export default function DisplaySettingsPopover({ settings, actions, active, onActivate, onDeactivate, container, disabled = false, triggerClassName = "" }) {
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
  return <Popover open={open} onOpenChange={next => { if (next) onActivate?.(); else if (active) onDeactivate?.(); setOpen(next); }}>
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
      {isValidElement(settings) ? cloneElement(settings, { appearanceControl: actions, sticky: false })
        : settings}
    </PopoverContent>
  </Popover>;
}
