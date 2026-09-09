import hardcoreMark from "@renderer/assets/brand/hardcore-monochrome.svg";

/** The original star in grayscale, alongside the app's regular type. */
export function Wordmark() {
  return (
    <span aria-label="Hardcore" className="app-no-drag flex min-w-0 items-center gap-2" role="img">
      <img alt="" className="size-7 shrink-0 object-contain" src={hardcoreMark} />
      <span className="truncate text-[17px] font-medium tracking-tight">Hardcore</span>
    </span>
  );
}
