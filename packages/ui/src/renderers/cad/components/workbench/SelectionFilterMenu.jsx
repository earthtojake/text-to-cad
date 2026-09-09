import { ListFilter } from 'lucide-react';
import { useContext } from 'react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuLabel, DropdownMenuSeparator } from '@hardcore/ui/primitives/dropdown-menu';
import { SELECTION_FILTERS } from '../../workbench/selectionFilter.js';
import { FileSheetPortalContext } from './FileSheet.js';

export default function SelectionFilterMenu({ value, onChange, disabled, compact }) {
  const boundary = useContext(FileSheetPortalContext);
  const label = SELECTION_FILTERS.find(item => item.id === value)?.label || 'All';
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label={`Selection filter: ${label}`} title={`Selection filter: ${label}`} disabled={disabled}
        className={`inline-flex h-6 shrink-0 items-center justify-center gap-1.5 rounded-sm text-xs hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 ${compact ? 'px-2' : 'w-6'} ${value !== 'all' ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/70'}`}>
        <ListFilter className="size-3" aria-hidden="true" />{compact && label}
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} collisionBoundary={boundary} collisionPadding={8} className="w-60 max-w-[min(240px,var(--radix-dropdown-menu-content-available-width))]" onEscapeKeyDown={event => event.stopPropagation()}>
      <DropdownMenuLabel>Selection filter</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
        {SELECTION_FILTERS.map(item => <DropdownMenuRadioItem key={item.id} value={item.id}>
          <span><span className="block">{item.label}</span><span className="block text-micro text-muted-foreground">{item.detail}</span></span>
        </DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
      <DropdownMenuSeparator />
      <p className="px-2 py-1.5 text-micro text-muted-foreground">Shift-click adds or removes from selection.</p>
    </DropdownMenuContent>
  </DropdownMenu>;
}
