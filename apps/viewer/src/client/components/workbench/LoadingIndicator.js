import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { prolongedLoadingMessage } from "@/workbench/viewerLoading.js";

// Shared by file opening and graphics initialization. Time is elapsed, never an ETA.
export default function LoadingIndicator({ headline, progress, operationKey = "" }) {
  const [timing, setTiming] = useState(() => ({ key: operationKey, started: Date.now(), elapsed: 0 }));
  useEffect(() => {
    const started = Date.now();
    setTiming({ key: operationKey, started, elapsed: 0 });
    const timer = setInterval(() => setTiming({ key: operationKey, started, elapsed: Date.now() - started }), 1000);
    return () => clearInterval(timer);
  }, [operationKey]);
  const elapsed = timing.key === operationKey ? timing.elapsed : 0;
  const waiting = Boolean(progress?.connectionLost);
  const explanation = prolongedLoadingMessage(elapsed, progress?.connectionLost);
  return (
    <div className="flex w-[22rem] max-w-[90vw] flex-col gap-3" role="status" aria-live="polite" data-viewer-loading="true">
      <div className="text-sm font-medium">{headline}</div>
      <div className="flex items-baseline justify-between gap-4 text-xs opacity-75">
        <span className="truncate">{waiting ? `Last step: ${progress?.label || "Reading model"}` : progress?.label || "Preparing view"}</span>
        <span className="shrink-0 tabular-nums">{progress?.counts || ""}</span>
      </div>
      <Progress value={progress?.percent ?? null} aria-label={progress?.label || "Preparing view"}
        className={waiting ? "[&_[data-slot=progress-indicator]]:[animation-play-state:paused]" : undefined} />
      {explanation ? <div className="text-xs opacity-75" aria-live="off">{explanation}</div> : null}
      {elapsed >= 10_000 && progress?.detail ? <div className="truncate text-xs opacity-60" title={progress.detail}>{progress.detail}</div> : null}
    </div>
  );
}
