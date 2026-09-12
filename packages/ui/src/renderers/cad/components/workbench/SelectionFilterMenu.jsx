import { ChevronDown, ListFilter } from 'lucide-react';
import { Fragment, useContext } from 'react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuLabel, DropdownMenuSeparator } from '@hardcore/ui/primitives/dropdown-menu';
import { SELECTION_FILTERS } from '../../workbench/selectionFilter.js';
import { FileSheetPortalContext } from './FileSheet.js';

export default function SelectionFilterMenu({ value, onChange, disabled, compact, fullWidth, options = SELECTION_FILTERS, menuLabel = 'Selection filter', hint = 'Shift-click adds or removes from selection.', triggerIcon: TriggerIcon = ListFilter }) {
  const boundary = useContext(FileSheetPortalContext);
  const label = options.find(item => item.id === value)?.label || options[0]?.label;
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label={`${menuLabel}: ${label}`} title={`${menuLabel}: ${label}`} disabled={disabled}
        className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 ${fullWidth ? 'w-full px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground' : `h-6 justify-center text-xs hover:bg-sidebar-accent ${compact ? 'px-2' : 'w-6'} ${value !== 'all' ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/70'}`}`}>
        <TriggerIcon className="size-3 shrink-0" aria-hidden="true" />{(compact || fullWidth) && label}{fullWidth && <ChevronDown className="ml-auto size-3 text-muted-foreground" aria-hidden="true" />}
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} collisionBoundary={boundary} collisionPadding={8} className="w-60 max-w-[min(240px,var(--radix-dropdown-menu-content-available-width))]" onEscapeKeyDown={event => event.stopPropagation()}>
      <DropdownMenuLabel>{menuLabel}</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
        {options.map((item, index) => <Fragment key={item.id}>
          {item.section && item.section !== options[index - 1]?.section && <><DropdownMenuSeparator /><DropdownMenuLabel>{item.section}</DropdownMenuLabel></>}
          <DropdownMenuRadioItem value={item.id}>
          <span><span className="block">{item.label}</span>{item.detail && <span className="block text-micro text-muted-foreground">{item.detail}</span>}</span>
        </DropdownMenuRadioItem></Fragment>)}
      </DropdownMenuRadioGroup>
      {hint && <><DropdownMenuSeparator /><p className="px-2 py-1.5 text-micro text-muted-foreground">{hint}</p></>}
    </DropdownMenuContent>
  </DropdownMenu>;
}
