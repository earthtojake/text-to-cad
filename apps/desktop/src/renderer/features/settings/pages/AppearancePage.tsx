/**
 * Appearance (plan §10): the theme cards, and the four things that ride on top
 * of them.
 *
 * Everything here is a token on `<html>` rather than a prop threaded through
 * the tree (`src/renderer/hooks/use-appearance.ts`), which is what lets the
 * viewer surface P4 mounts inside the app inherit the same accent and the same
 * scale without knowing this page exists.
 */
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "cn";

import {
  SelectRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  useRowMatch,
} from "@renderer/features/settings/SettingCard";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { ACCENTS, fontAvailable } from "@renderer/hooks/use-appearance";
import { isMac } from "@renderer/lib/platform";
import type { AccentColor, CodeFont, ThemePreference, UiFontSize } from "@shared/types";

const THEMES: { value: ThemePreference; label: string; icon: React.ReactNode }[] = [
  { value: "system", label: "System", icon: <Monitor className="size-4" /> },
  { value: "light", label: "Light", icon: <Sun className="size-4" /> },
  { value: "dark", label: "Dark", icon: <Moon className="size-4" /> },
];

const ACCENT_LABELS: Record<AccentColor, string> = {
  neutral: "Neutral",
  blue: "Blue",
  violet: "Violet",
  green: "Green",
  orange: "Orange",
  rose: "Rose",
};

const FONT_SIZES: { value: UiFontSize; label: string }[] = [
  { value: "small", label: "Small" },
  { value: "default", label: "Default" },
  { value: "large", label: "Large" },
];

export function AppearancePage() {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();

  const jetbrains = fontAvailable("JetBrains Mono");
  const codeFonts: { value: CodeFont; label: string }[] = [
    { value: "system", label: "System monospace" },
    {
      value: "jetbrains-mono",
      label: jetbrains ? "JetBrains Mono" : "JetBrains Mono (not installed)",
    },
  ];

  return (
    <>
      <SettingCard title="Theme">
        <ThemeRow onSelect={(theme) => patch({ theme })} value={settings.theme} />
        <AccentRow
          onSelect={(accentColor) => patch({ accentColor })}
          value={settings.accentColor}
        />
      </SettingCard>

      <SettingCard title="Text">
        <SelectRow
          description="The size everything else is measured against."
          keywords="scale zoom bigger smaller"
          onChange={(uiFontSize) => patch({ uiFontSize })}
          options={FONT_SIZES}
          title="UI font size"
          value={settings.uiFontSize}
          width="w-[160px]"
        />
        <SelectRow
          description={
            jetbrains
              ? "Used by the editor, diffs, terminals and code blocks."
              : "Used by the editor, diffs, terminals and code blocks. JetBrains Mono is not installed on this machine."
          }
          keywords="monospace editor terminal jetbrains"
          onChange={(codeFont) => patch({ codeFont })}
          options={codeFonts}
          title="Code font"
          value={settings.codeFont}
          width="w-[220px]"
        />
        <SettingRow
          description="How the code font looks at this size."
          keywords="preview sample monospace"
          title="Preview"
        >
          <pre className="overflow-x-auto rounded-lg border bg-muted/40 px-3 py-2.5 font-mono text-xs leading-relaxed">
            <code data-selectable>{SAMPLE}</code>
          </pre>
        </SettingRow>
      </SettingCard>

      <SettingCard title="Motion and materials">
        <SwitchRow
          checked={settings.reduceMotion}
          description="Cut transitions and animations to nothing, whatever the system is set to."
          keywords="animation transition accessibility"
          onChange={(reduceMotion) => patch({ reduceMotion })}
          title="Reduce motion"
        />
        {isMac ? (
          <SwitchRow
            checked={settings.translucentSidebar}
            description="Let the desktop show through the sidebar. Costs a compositing pass, so it is off by default."
            keywords="vibrancy blur transparent"
            onChange={(translucentSidebar) => patch({ translucentSidebar })}
            title="Translucent sidebar"
          />
        ) : null}
      </SettingCard>
    </>
  );
}

const SAMPLE = `@step
def bracket(width: float = 40.0):
    return Box(width, 20, 6) - Cylinder(3, 6)`;

/** The three theme cards. A row of its own so search can hide it with the rest. */
function ThemeRow({
  value,
  onSelect,
}: {
  value: ThemePreference;
  onSelect: (theme: ThemePreference) => void;
}) {
  const matched = useRowMatch("Theme", "System light dark appearance colour scheme");
  if (!matched) {
    return null;
  }
  return (
    <div className="grid grid-cols-3 gap-3 p-4">
      {THEMES.map((option) => (
        <button
          aria-label={option.label}
          aria-pressed={value === option.value}
          className={cn(
            "flex flex-col items-center gap-2 rounded-lg border px-3 py-4 text-xs transition-colors",
            value === option.value ? "border-primary bg-accent" : "hover:bg-accent/50",
          )}
          key={option.value}
          onClick={() => onSelect(option.value)}
          type="button"
        >
          <span className="text-muted-foreground">{option.icon}</span>
          {option.label}
        </button>
      ))}
    </div>
  );
}

function AccentRow({
  value,
  onSelect,
}: {
  value: AccentColor;
  onSelect: (accent: AccentColor) => void;
}) {
  const matched = useRowMatch(
    "Accent",
    "Buttons, selection and focus rings",
    "colour color primary highlight blue violet green orange rose neutral",
  );
  if (!matched) {
    return null;
  }
  return (
    <div className="flex items-center justify-between gap-6 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm">Accent</p>
        <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
          Buttons, selection and focus rings. Neutral is the stock theme.
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {(Object.keys(ACCENT_LABELS) as AccentColor[]).map((accent) => (
          <button
            aria-label={ACCENT_LABELS[accent]}
            aria-pressed={value === accent}
            className={cn(
              "size-6 rounded-full border transition-transform",
              value === accent
                ? "ring-2 ring-ring ring-offset-2 ring-offset-card"
                : "hover:scale-110",
            )}
            key={accent}
            onClick={() => onSelect(accent)}
            // The neutral swatch has no override to show, so it shows the
            // token itself — which is exactly what choosing it restores.
            style={{
              backgroundColor: accent === "neutral" ? "var(--primary)" : ACCENTS[accent].swatch,
            }}
            title={ACCENT_LABELS[accent]}
            type="button"
          />
        ))}
      </div>
    </div>
  );
}
