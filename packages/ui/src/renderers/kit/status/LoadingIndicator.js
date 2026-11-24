import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { useEffect, useState } from "react";
import { useI18n } from "@cad/ui/i18n";
import { statusLabel } from "./statusLabels.js";
import LoadingStep from "../../../loading/LoadingStep.jsx";

// Shared by file opening and graphics initialization: the one indicator (`loading/LoadingStep.jsx`), its step line
// what is actually happening. There is no headline and no clock; a long wait only adds the step's detail line, and a
// lost connection its waiting line, the bar held.
export default function LoadingIndicator({ progress, operationKey = "" }) {
  const { t } = useI18n();
  // The operation that has been loading for over ten seconds, if any: its detail line shows.
  const [longKey, setLongKey] = useState(null);
  useEffect(() => {
    const timer = setTimeout(() => setLongKey(operationKey), 10_000);
    return () => clearTimeout(timer);
  }, [operationKey]);
  const long = longKey === operationKey;
  const waiting = Boolean(progress?.connectionLost);
  const step = statusLabel(progress?.label, t);
  const label = waiting ? t("loading.lastStep", { label: step || t("loading.openingModel") }) : step || t("loading.preparingView");
  return (
    <LoadingStep label={label} counts={progress?.counts || ""} percent={progress?.percent ?? null} paused={waiting} data-viewer-loading="true">
      {waiting ? <div aria-live="off">{t("loading.waitingForResponse")}</div> : null}
      {long && progress?.detail ? <TooltipHint content={progress.detail}><div className="truncate">{progress.detail}</div></TooltipHint> : null}
    </LoadingStep>
  );
}
