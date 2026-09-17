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
import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "@hardcore/ui/primitives/dropdown-menu";
import { COLOR_SCHEMES } from "../../ui/colorScheme.js";

/** @param {{ colorSchemePreference?: string, onColorSchemePreferenceChange?: (value: string) => void }} props */
export default function ViewerTopBar({ colorSchemePreference = "system", onColorSchemePreferenceChange = undefined }) {
  const AppearanceIcon = colorSchemePreference === "light" ? Sun : colorSchemePreference === "dark" ? Moon : Monitor;
  const label = `Appearance: ${COLOR_SCHEMES.find(option => option.id === colorSchemePreference)?.label || "System"}`;
  return (
    <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-2 text-foreground">
      <img alt="" aria-hidden className="size-4 shrink-0 rounded-[3px]" src={faviconUrl} />
      <span className="truncate text-[13px] tracking-tight">Hardcore</span>
      <div className="flex-1" />
      <div className="flex shrink-0 items-center gap-0.5">
        <ViewerLinks />
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="size-6 text-muted-foreground hover:text-foreground" aria-label={label} title={label}><AppearanceIcon className="size-3.5" aria-hidden="true" /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-36">
            <DropdownMenuRadioGroup value={colorSchemePreference} onValueChange={onColorSchemePreferenceChange}>
              {COLOR_SCHEMES.map(option => <DropdownMenuRadioItem key={option.id} value={option.id} className="text-xs">{option.label}</DropdownMenuRadioItem>)}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
