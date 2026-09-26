import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { Popover, PopoverTrigger, PopoverContent } from "@hardcore/ui/primitives/popover";
import { useEffect, useState } from 'react';
import { LoaderCircle, RotateCcw } from 'lucide-react';
import { cn } from '@hardcore/ui/utils';
import { Button } from '@hardcore/ui/primitives/button';

// Presentation only: the caller owns placement. No overlay, scene access or
// control disabling. Delay avoids flashing a spinner for next-frame updates.
export function ViewUpdateStatus({ status, onRetry, className, style = undefined, delayMs = 150 }) {
  const mobile = useViewerMobile();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!status.pending) { setVisible(false); return; }
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [status.pending, delayMs]);
  if (!status.error && !visible) return null;
  const label = status.error ? `Couldn’t update view: ${status.error}` : status.label || 'Updating view…';
  if (mobile) return <Popover>
    <PopoverTrigger asChild><Button variant="ghost" size="icon-xs" className="size-6 shrink-0" aria-label={label}  data-view-update-status>
      {status.error ? <RotateCcw className="size-3.5" /> : <LoaderCircle className="size-3.5 animate-spin" />}
    </Button></PopoverTrigger>
    <PopoverContent className="w-max max-w-64 px-3 py-2 text-tiny" align="start">
      <span role={status.error ? 'alert' : 'status'}>{label}</span>
      {status.error && <Button variant="ghost" size="sm" onClick={onRetry}>Retry</Button>}
    </PopoverContent>
  </Popover>;
  return <div style={style} className={cn('pointer-events-auto flex min-w-0 items-center gap-2 bg-transparent text-xs text-muted-foreground', className)}
    role={status.error ? 'alert' : 'status'} aria-live="polite" data-view-update-status>
    {status.error ? <><TooltipHint content={status.error}><span >Couldn’t update view</span></TooltipHint>
      <Button size="icon-xs" variant="ghost" aria-label="Retry view update" onClick={onRetry}><RotateCcw className="size-3.5" /></Button></>
      : <><LoaderCircle className="size-3.5 shrink-0 animate-spin" aria-hidden="true" /><span className="truncate">{status.label || 'Updating view…'}</span></>}
  </div>;
}
