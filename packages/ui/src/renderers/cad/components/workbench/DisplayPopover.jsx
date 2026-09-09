import { useContext, useState } from 'react';
import { Eye, X } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@hardcore/ui/primitives/popover';
import { FileSheetPortalContext } from './FileSheet.js';

export default function DisplayPopover({ children, disabled }) {
  const [open, setOpen] = useState(false);
  const boundary = useContext(FileSheetPortalContext);
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
      <button type="button" aria-label="Display" title="Display" disabled={disabled}
        className="grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50 data-[state=open]:bg-sidebar-accent">
        <Eye className="size-3" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent aria-label="Display settings" align="end" sideOffset={8} collisionBoundary={boundary} collisionPadding={8}
      onEscapeKeyDown={event => event.stopPropagation()}
      className="w-60 max-w-[calc(100vw-1rem)] max-h-[var(--radix-popover-content-available-height)] overflow-y-auto p-1">
      <div className="flex items-center justify-between px-2 py-1.5 text-sm font-medium">
        <span>Display</span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close Display" className="rounded-sm p-1 text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><X className="size-3" aria-hidden="true" /></button>
      </div>
      <div className="-mx-1 my-1 h-px bg-border" />
      {children}
    </PopoverContent>
  </Popover>;
}
