/**
 * The web app's own bar, above the shared shell.
 *
 * The shell below it — the nav row, the breadcrumb, the panel toggles — is the
 * desktop app's file tab, drawn from `shell/`. Anything this distribution has
 * that a file tab does not belongs up here instead of in that row, so the two
 * apps keep ONE shell with one set of controls: the name and mark on the left,
 * the release chip and the links on the right.
 *
 * Its height is the nav row's (`h-9`), so the two rows read as one chrome
 * rather than a bar with a bar under it.
 */
import faviconUrl from "../../assets/favicon.ico";

import ViewerLinks from "./ViewerLinks";

export default function ViewerTopBar() {
  return (
    <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-2 text-foreground">
      <img alt="" aria-hidden className="size-4 shrink-0 rounded-[3px]" src={faviconUrl} />
      <span className="truncate text-[13px] font-medium tracking-tight">text-to-cad</span>
      <div className="flex-1" />
      <div className="flex shrink-0 items-center gap-0.5">
        <ViewerLinks />
      </div>
    </header>
  );
}
