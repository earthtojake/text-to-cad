import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { Popover, PopoverTrigger, PopoverContent } from "@text-to-cad/ui/primitives/popover";
import { useEffect, useState } from 'react';
import { Eye, LoaderCircle, RotateCcw } from 'lucide-react';
import { cn } from '@text-to-cad/ui/utils';
import { Button } from '@text-to-cad/ui/primitives/button';
import { useI18n } from '@text-to-cad/ui/i18n';
import { isProgressKey } from './progressEvent.js';
import { statusLine } from './statusLabels.js';

// Presentation only: the caller owns placement. No overlay, scene access or
// control disabling. Delay avoids flashing a spinner for next-frame updates.
const SHOW_AFTER_MS = 150;

/** A newer revision of the file loading behind the one on screen: the view stays usable meanwhile. */
export const MODEL_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating model…" });

/** What loads behind the view, from the loading frame (`loadingProgress`): the engine's progress event
 * says its stage, counted where it has a count (a build's "Building geometry…", "Writing files 1/2…";
 * `progressEvent.js`); cadgen meshing parts its store lacked (a cold open, drawn as the parts arrive)
 * says so, counted; anything else is the model updating. */
export function modelUpdateStatus(progress) {
  if (isProgressKey(progress?.label)) return { pending: true, label: progress.label, counts: progress.counts || "" };
  if (progress?.label !== "Meshing parts") return MODEL_UPDATE_STATUS;
  return { pending: true, label: `Meshing parts${progress.counts ? ` ${progress.counts}` : ""}…` };
}

export function ViewUpdateStatus({ status, onRetry, className }) {
  const mobile = useViewerMobile();
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!status.pending) { setVisible(false); return; }
    const timer = setTimeout(() => setVisible(true), SHOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [status.pending]);
  if (!status.error && !visible) return null;
  const updating = statusLine(status, t) || t('viewUpdate.updatingView');
  const label = status.error ? t('viewUpdate.failedWith', { error: status.error }) : updating;
  if (mobile) return <Popover>
    <PopoverTrigger asChild><Button variant="ghost" size="icon-xs" className="pointer-events-auto size-6 shrink-0" aria-label={label}  data-view-update-status>
      {status.error ? <RotateCcw className="size-3.5" /> : <LoaderCircle className="size-3.5 animate-spin" />}
    </Button></PopoverTrigger>
    <PopoverContent className="w-max max-w-64 px-3 py-2 text-tiny" align="start">
      <span role={status.error ? 'alert' : 'status'}>{label}</span>
      {status.error && <Button variant="ghost" size="sm" onClick={onRetry}>{t('alert.retry')}</Button>}
    </PopoverContent>
  </Popover>;
  return <div className={cn('flex min-w-0 items-center gap-2 bg-transparent text-xs text-muted-foreground', status.error ? 'pointer-events-auto' : 'pointer-events-none', className)}
    role={status.error ? 'alert' : 'status'} aria-live="polite" data-view-update-status>
    {status.error ? <><TooltipHint content={status.error}><span >{t('viewUpdate.failed')}</span></TooltipHint>
      <Button size="icon-xs" variant="ghost" aria-label={t('viewUpdate.retry')} onClick={onRetry}><RotateCcw className="size-3.5" /></Button></>
      : <><LoaderCircle className="size-3.5 shrink-0 animate-spin" aria-hidden="true" /><span className="truncate">{updating}</span></>}
  </div>;
}

/**
 * The model on screen is a build's own preview revision, not the saved file:
 * said where the update status is said, for as long as it is drawn -- through the rest of the build,
 * and under the alert of one that failed -- and gone once the saved file replaces it in place.
 */
export function ViewPreviewLabel({ className }) {
  const { t } = useI18n();
  return <div className={cn('pointer-events-auto flex min-w-0 items-center gap-1.5 bg-transparent text-xs font-medium text-foreground', className)}
    role="status" aria-live="polite" data-view-preview-label>
    <TooltipHint content={t("status.buildPreviewHint")}>
      <span className="flex items-center gap-1.5"><Eye className="size-3.5 shrink-0" aria-hidden="true" />{t("status.buildPreview")}</span>
    </TooltipHint>
  </div>;
}
