import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import LoadingIcon from "@text-to-cad/ui/loading-icon";
import { useContext, useEffect, useState } from "react";
import { ViewerHostContext } from "../../../host/context.js";
import { Progress } from "@text-to-cad/ui/primitives/progress";

// Shared by file opening and graphics initialization. There is no headline and no clock:
// that a model is opening is plain from the mark, and the step line under it says what is
// actually happening. A long wait only adds the step's detail line.
export default function LoadingIndicator({ progress, operationKey = "" }) {
  // The operation that has been loading for over ten seconds, if any: its detail line shows.
  const [longKey, setLongKey] = useState(null);
  useEffect(() => {
    const timer = setTimeout(() => setLongKey(operationKey), 10_000);
    return () => clearTimeout(timer);
  }, [operationKey]);
  const long = longKey === operationKey;
  const waiting = Boolean(progress?.connectionLost);
  const reducedMotion = useContext(ViewerHostContext)?.environment.reducedMotion === true;
  return (
    <div className="flex w-[22rem] max-w-[90vw] flex-col gap-3" role="status" aria-live="polite" data-viewer-loading="true">
      <LoadingIcon size={80} active={!waiting} reducedMotion={reducedMotion} className="self-center" />
      <div className="flex items-baseline justify-between gap-4 text-xs opacity-75">
        <span className="truncate">{waiting ? `Last step: ${progress?.label || "Opening model"}` : progress?.label || "Preparing view"}</span>
        <span className="shrink-0 tabular-nums">{progress?.counts || ""}</span>
      </div>
      <Progress value={progress?.percent ?? null} aria-label={progress?.label || "Preparing view"}
        className={waiting ? "[&_[data-slot=progress-indicator]]:[animation-play-state:paused]" : undefined} />
      {waiting ? <div className="text-xs opacity-75" aria-live="off">Waiting for a response. Retrying…</div> : null}
      {long && progress?.detail ? <TooltipHint content={progress.detail}><div className="truncate text-xs opacity-60" >{progress.detail}</div></TooltipHint> : null}
    </div>
  );
}
