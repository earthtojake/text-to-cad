import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import LoadingIcon from "@text-to-cad/ui/loading-icon";
import { useSettings } from "@renderer/state/settings";

/** The live status keeps its existing words; only actual work animates. */
export function StatusLine({ text, active }: { text: string; active: boolean }) {
  const reducedMotion = useSettings((state) => state.settings?.reduceMotion ?? false);
  return (
    // The whole line is a hover away only when it is clipped; the full text is in the DOM either way.
    <TooltipHint content={text} overflowOnly side="top">
      <p className="not-prose mt-1 flex min-w-0 items-center gap-1.5 px-1.5 text-[13px] leading-5 text-muted-foreground" data-status-line>
        <LoadingIcon active={active} size={24} reducedMotion={reducedMotion} />
        <span className="min-w-0 truncate">{text}</span>
      </p>
    </TooltipHint>
  );
}
