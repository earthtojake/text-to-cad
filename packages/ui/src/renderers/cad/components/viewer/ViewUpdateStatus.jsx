import { useEffect, useState } from 'react';
import { LoaderCircle, RotateCcw } from 'lucide-react';
import { cn } from '@hardcore/ui/utils';
import { Button } from '@hardcore/ui/primitives/button';

// Presentation only: the caller owns placement. No overlay, scene access or
// control disabling. Delay avoids flashing a spinner for next-frame updates.
export function ViewUpdateStatus({ status, onRetry, className, delayMs = 150 }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!status.pending) { setVisible(false); return; }
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [status.pending, delayMs]);
  if (!status.error && !visible) return null;
  return <div className={cn('pointer-events-auto flex items-center gap-2 rounded-md border border-border bg-background/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm', className)}
    role={status.error ? 'alert' : 'status'} aria-live="polite" data-view-update-status>
    {status.error ? <><span title={status.error}>Couldn’t update view</span>
      <Button size="icon-xs" variant="ghost" aria-label="Retry view update" onClick={onRetry}><RotateCcw className="size-3.5" /></Button></>
      : <><LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" /><span>{status.label || 'Updating view…'}</span></>}
  </div>;
}
