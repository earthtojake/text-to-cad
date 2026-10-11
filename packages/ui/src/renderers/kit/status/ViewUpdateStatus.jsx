import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { Popover, PopoverTrigger, PopoverContent } from "@text-to-cad/ui/primitives/popover";
import { useEffect, useState } from 'react';
import { LoaderCircle, RotateCcw } from 'lucide-react';
import { cn } from '@text-to-cad/ui/utils';
import { Button } from '@text-to-cad/ui/primitives/button';

// Presentation only: the caller owns placement. No overlay, scene access or
// control disabling. Delay avoids flashing a spinner for next-frame updates.
const SHOW_AFTER_MS = 150;

/** A newer revision of the file loading behind the one on screen: the view stays usable meanwhile. */
export const MODEL_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating model…" });

/** What loads behind the view, from the loading frame (`loadingProgress`): cadgen meshing parts its
 * store lacked (a cold open, drawn as the parts arrive) says so, counted; anything else is the
 * model updating. */
export function modelUpdateStatus(progress) {
  if (progress?.label !== "Meshing parts") return MODEL_UPDATE_STATUS;
  return { pending: true, label: `Meshing parts${progress.counts ? ` ${progress.counts}` : ""}…` };
}

export function ViewUpdateStatus({ status, onRetry, className }) {
  const mobile = useViewerMobile();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!status.pending) { setVisible(false); return; }
    const timer = setTimeout(() => setVisible(true), SHOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [status.pending]);
  if (!status.error && !visible) return null;
  const label = status.error ? `Couldn’t update view: ${status.error}` : status.label || 'Updating view…';
  if (mobile) return <Popover>
    <PopoverTrigger asChild><Button variant="ghost" size="icon-xs" className="pointer-events-auto size-6 shrink-0" aria-label={label}  data-view-update-status>
      {status.error ? <RotateCcw className="size-3.5" /> : <LoaderCircle className="size-3.5 animate-spin" />}
    </Button></PopoverTrigger>
    <PopoverContent className="w-max max-w-64 px-3 py-2 text-tiny" align="start">
      <span role={status.error ? 'alert' : 'status'}>{label}</span>
      {status.error && <Button variant="ghost" size="sm" onClick={onRetry}>Retry</Button>}
    </PopoverContent>
  </Popover>;
  return <div className={cn('flex min-w-0 items-center gap-2 bg-transparent text-xs text-muted-foreground', status.error ? 'pointer-events-auto' : 'pointer-events-none', className)}
    role={status.error ? 'alert' : 'status'} aria-live="polite" data-view-update-status>
    {status.error ? <><TooltipHint content={status.error}><span >Couldn’t update view</span></TooltipHint>
      <Button size="icon-xs" variant="ghost" aria-label="Retry view update" onClick={onRetry}><RotateCcw className="size-3.5" /></Button></>
      : <><LoaderCircle className="size-3.5 shrink-0 animate-spin" aria-hidden="true" /><span className="truncate">{status.label || 'Updating view…'}</span></>}
  </div>;
}
