import { Monitor, Moon, Sun } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@hardcore/ui/primitives/select";
import { COLOR_SCHEMES } from "../../ui/colorScheme.js";

const ICONS = { system: Monitor, light: Sun, dark: Moon };
// Host-owned appearance preference, placed beside Projection by the shared sheet.
/** @param {{ colorSchemePreference?: string, resolvedColorSchemeMode?: 'light' | 'dark', onColorSchemePreferenceChange?: (value: string) => void, fullscreen?: boolean }} props */
export default function ViewerAppearance({ colorSchemePreference = "system", resolvedColorSchemeMode = "light", onColorSchemePreferenceChange = undefined, fullscreen = false }) {
  if (fullscreen) return null;
  const displayedMode = colorSchemePreference === "system" ? resolvedColorSchemeMode : colorSchemePreference;
  const Icon = ICONS[displayedMode] || Sun;
  return <Select value={colorSchemePreference} onValueChange={onColorSchemePreferenceChange}>
    <SelectTrigger aria-label="Appearance"  size="sm" className="!h-7 min-w-0 gap-1 px-2 !text-tiny [&_svg]:size-3.5">
      <span className="flex min-w-0 items-center gap-1"><Icon className="size-3.5 shrink-0" aria-hidden="true" /><SelectValue>{displayedMode === "dark" ? "Dark" : "Light"}</SelectValue></span>
    </SelectTrigger>
    <SelectContent>
      {COLOR_SCHEMES.map(option => {
        const OptionIcon = ICONS[option.id];
        return <SelectItem key={option.id} value={option.id} icon={<OptionIcon className="size-3.5" />}>{option.label}</SelectItem>;
      })}
    </SelectContent>
  </Select>;
}
