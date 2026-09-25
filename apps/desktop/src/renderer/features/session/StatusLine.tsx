import LoadingIcon from "@hardcore/ui/loading-icon";
import { useSettings } from "@renderer/state/settings";

/** The live status keeps its existing words; only actual work animates. */
export function StatusLine({ text, active }: { text: string; active: boolean }) {
  const reducedMotion = useSettings((state) => state.settings?.reduceMotion ?? false);
  return (
    <p className="not-prose mt-1 flex min-w-0 items-center gap-1.5 px-1.5 text-[13px] leading-5 text-muted-foreground" data-status-line title={text}>
      <LoadingIcon active={active} size={24} reducedMotion={reducedMotion} />
      <span className="min-w-0 truncate">{text}</span>
    </p>
  );
}
