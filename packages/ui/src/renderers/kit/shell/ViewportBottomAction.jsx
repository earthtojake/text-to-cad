import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

const ACTION_CLASS = "pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35";
const METRICS_CLASS = "h-9 w-fit min-w-0 max-w-full sm:max-w-[min(28rem,calc(100%-16rem))] shrink overflow-hidden px-4 text-xs max-sm:w-full max-sm:pr-32";
const COMPOSER_METRICS_CLASS = "h-9 w-fit min-w-0 max-w-full shrink overflow-hidden px-4 text-xs";

/**
 * The viewport's bottom action: the one button the active tool offers, centred
 * over the bottom edge. `composer` is a host that has a prompt composer docked
 * under the viewport, which the button clears.
 */
export default function ViewportBottomAction({ label, title = label, disabled = false, onInvoke, composer = false, children = null }) {
  return (
    <div className={cn("pointer-events-none absolute inset-x-4 z-20 flex min-w-0 justify-center", composer ? "bottom-36" : "bottom-4")}>
      <Button type="button" variant="default" size="sm" className={cn(ACTION_CLASS, composer ? COMPOSER_METRICS_CLASS : METRICS_CLASS)}
        disabled={disabled} onClick={() => void onInvoke?.()} title={title}>
        <span className="block min-w-0 max-w-full truncate">{label}</span>
      </Button>
      {children ? <div className="pointer-events-auto ml-2">{children}</div> : null}
    </div>
  );
}

/** Draw's bottom action: the view with its ink, to the prompt or the clipboard. */
export function drawingCaptureAction({ composer = false, disabled = false, onInvoke }) {
  return {
    label: composer ? "Add to Prompt" : "Copy Drawing",
    title: composer ? "Add the view and its drawing to the prompt" : "Copy the view and its drawing to the clipboard",
    disabled, onInvoke
  };
}
