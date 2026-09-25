import { FLOATING_TOOL_BAR_SURFACE_CLASS } from "../../../kit/tools/FloatingToolBar.js";
import { ChevronDown, ListFilter } from 'lucide-react';
import { Fragment } from 'react';
import { DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuLabel, DropdownMenuSeparator } from '@hardcore/ui/primitives/dropdown-menu';
import { SELECTION_FILTERS } from '../../workbench/selectionFilter.js';
import ToolPopover from "../../../kit/tools/ToolPopover.jsx";

export default function SelectionFilterMenu({ value, onChange, disabled, compact, fullWidth, options = SELECTION_FILTERS, menuLabel = 'Selection filter', hint = 'Shift-click adds or removes from selection.', triggerIcon: TriggerIcon = ListFilter, trigger = null }) {
  const label = options.find(item => item.id === value)?.label || options[0]?.label;
  const button = trigger || <button type="button" aria-label={`${menuLabel}: ${label}`}  disabled={disabled}
        className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 ${fullWidth ? 'w-full px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground' : `h-6 justify-center text-sm hover:bg-sidebar-accent ${compact ? 'px-2' : 'w-6'} ${value !== 'all' ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/70'}`}`}>
        <TriggerIcon className="size-3 shrink-0" aria-hidden="true" />{(compact || fullWidth) && label}{fullWidth && <ChevronDown className="ml-auto size-3 text-muted-foreground" aria-hidden="true" />}
      </button>;
  return <ToolPopover trigger={button} label={menuLabel} className="w-60">
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
 * everything one, and anything else that tool carries (a notice, a measurement list).
 *
 * @param {{ options: {id: string, label: string}[] | null, value: string | null, active: boolean,
 *   notice?: string, panel?: import("react").ReactNode }} props
 */
export function ToolFilterNote({ options, value, active, notice = "", panel = null }) {
  if (!active) return null;
  const chosen = options && value && value !== "all" ? options.find(item => item.id === value)?.label : "";
  if (!chosen && !notice && !panel) return null;
  return <>
    {chosen ? <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>{chosen}</div> : null}
    {notice ? <p role="status" className="max-w-56 rounded-md border bg-background px-2 py-1 text-micro text-muted-foreground shadow-sm">{notice}</p> : null}
    {panel}
  </>;
}
