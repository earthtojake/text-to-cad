import { FLOATING_TOOL_BAR_SURFACE_CLASS } from "../../../kit/tools/FloatingToolBar.js";
import { Fragment } from 'react';
import { DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuLabel, DropdownMenuSeparator } from '@hardcore/ui/primitives/dropdown-menu';
import { SELECTION_FILTERS } from '../../workbench/selectionFilter.js';
import ToolPopover from "../../../kit/tools/ToolPopover.jsx";

/** A tool's filter menu, opened from the tool's own button (`trigger`, the toolbar's). */
export default function SelectionFilterMenu({ value, onChange, trigger, options = SELECTION_FILTERS, menuLabel = 'Selection filter', hint = 'Shift-click adds or removes from selection.' }) {
  return <ToolPopover trigger={trigger} label={menuLabel} className="w-60">
      <DropdownMenuLabel>{menuLabel}</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
        {options.map((item, index) => <Fragment key={item.id}>
          {item.section && item.section !== options[index - 1]?.section && <><DropdownMenuSeparator /><DropdownMenuLabel>{item.section}</DropdownMenuLabel></>}
          <DropdownMenuRadioItem value={item.id}>
          <span><span className="block">{item.label}</span>{item.detail && <span className="block text-micro text-muted-foreground">{item.detail}</span>}</span>
        </DropdownMenuRadioItem></Fragment>)}
      </DropdownMenuRadioGroup>
      {hint && <><DropdownMenuSeparator /><p className="px-2 py-1.5 text-micro text-muted-foreground">{hint}</p></>}
  </ToolPopover>;
}

/**
 * What a tool adds under the strip while it is in hand: the chosen filter, when it is not the
 * everything one, and a notice when the tool has something to say.
 *
 * @param {{ options: {id: string, label: string}[] | null, value: string | null, active: boolean,
 *   notice?: string }} props
 */
export function ToolFilterNote({ options, value, active, notice = "" }) {
  if (!active) return null;
  const chosen = options && value && value !== "all" ? options.find(item => item.id === value)?.label : "";
  if (!chosen && !notice) return null;
  return <>
    {chosen ? <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>{chosen}</div> : null}
    {notice ? <p role="status" className="max-w-56 rounded-md border bg-background px-2 py-1 text-micro text-muted-foreground shadow-sm">{notice}</p> : null}
  </>;
}
