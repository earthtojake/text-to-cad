import textToCadMark from "@renderer/assets/brand/text-to-cad-star.svg";

/** The original star in blue, alongside the app's regular type. */
export function Wordmark() {
  return (
    <span aria-label="text-to-cad" className="app-no-drag flex min-w-0 items-center gap-2" role="img">
      <img alt="" className="size-7 shrink-0 object-contain" src={textToCadMark} />
      <span className="truncate text-[17px] font-medium tracking-tight">text-to-cad</span>
    </span>
  );
}
