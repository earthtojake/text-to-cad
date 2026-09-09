import LoadingIcon from "@hardcore/ui/loading-icon";

/** The live status keeps its existing words; only actual work animates. */
export function StatusLine({ text, active }: { text: string; active: boolean }) {
  return (
    <p className="not-prose mt-1 flex min-w-0 items-center gap-1.5 px-1.5 text-[13px] leading-5 text-muted-foreground" data-status-line title={text}>
      <LoadingIcon active={active} size={24} />
      <span className="min-w-0 truncate">{text}</span>
    </p>
  );
}
