import { Monitor, Moon, Sun } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@text-to-cad/ui/primitives/select";
import { useI18n } from "@text-to-cad/ui/i18n";
import { COLOR_SCHEMES } from "../../ui/colorScheme.js";
import { LOCALES, changeLocale } from "../../ui/locale.js";

const ICONS = { system: Monitor, light: Sun, dark: Moon };
// Host-owned appearance and language preferences, placed beside Projection by the shared sheet.
/** @param {{ colorSchemePreference?: string, resolvedColorSchemeMode?: 'light' | 'dark', onColorSchemePreferenceChange?: (value: string) => void }} props */
export default function ViewerAppearance({ colorSchemePreference = "system", resolvedColorSchemeMode = "light", onColorSchemePreferenceChange = undefined }) {
  const { locale, t } = useI18n();
  const displayedMode = colorSchemePreference === "system" ? resolvedColorSchemeMode : colorSchemePreference;
  const Icon = ICONS[displayedMode] || Sun;
  return <div className="flex min-w-0 flex-col gap-1">
    <Select value={colorSchemePreference} onValueChange={onColorSchemePreferenceChange}>
      <SelectTrigger aria-label={t("appearance.label")} size="sm" className="!h-7 min-w-0 gap-1 px-2 !text-tiny [&_svg]:size-3.5">
        <span className="flex min-w-0 items-center gap-1"><Icon className="size-3.5 shrink-0" aria-hidden="true" /><SelectValue>{displayedMode === "dark" ? t("appearance.dark") : t("appearance.light")}</SelectValue></span>
      </SelectTrigger>
      <SelectContent>
        {COLOR_SCHEMES.map(option => {
          const OptionIcon = ICONS[option.id];
          return <SelectItem key={option.id} value={option.id} icon={<OptionIcon className="size-3.5" />}>{t(`appearance.${option.id}`)}</SelectItem>;
        })}
      </SelectContent>
    </Select>
    {/* Each language under its own name, whatever the page is reading in. */}
    <Select value={locale} onValueChange={changeLocale}>
      <SelectTrigger aria-label={t("language.label")} size="sm" className="!h-7 min-w-0 gap-1 px-2 !text-tiny [&_svg]:size-3.5">
        <SelectValue>{t(`language.${locale}`)}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {LOCALES.map(id => <SelectItem key={id} value={id}>{t(`language.${id}`)}</SelectItem>)}
      </SelectContent>
    </Select>
  </div>;
}
