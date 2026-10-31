import { X } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@text-to-cad/ui/primitives/select";
import { cn } from "@text-to-cad/ui/utils";
import { useI18n } from "@text-to-cad/ui/i18n";
import { FILE_SIDEBAR_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { FILE_SHEET_SELECT_TRIGGER_CLASSES, FileSheetSettingRow, FileSheetSettingsSection } from "../inspector/FileSheet.js";
import { ORBIT_SPEEDS } from "../tools/PlaybackMenu.jsx";

/**
 * Preview's settings, docked at the view's right edge under its corner (closed as Preview
 * opens; its settings button and this X put it away): **Orbit** — the camera turning about the
 * model, on or off (preview's own, off each time it opens) and its speed (the file's) — then
 * Render's own settings (`render`, the Display settings' Render page: lighting, background, floor).
 *
 * @param {{ orbit: boolean, onOrbitChange(value: boolean): void, speed: number, onSpeedChange(value: number): void,
 *   onClose(): void, render: import("react").ReactNode }} props
 */
export default function PreviewSettings({ orbit, onOrbitChange, speed, onSpeedChange, onClose, render }) {
  const { t } = useI18n();
  const speeds = ORBIT_SPEEDS.includes(speed) ? ORBIT_SPEEDS : [...ORBIT_SPEEDS, speed].sort((a, b) => a - b);
  return <div role="region" aria-label={t("preview.settings")} data-preview-settings-panel=""
    className={cn("pointer-events-auto flex max-h-full w-60 min-h-0 flex-col overflow-hidden rounded-md text-tiny", FILE_SIDEBAR_SURFACE_CLASS)}>
    <div className="flex h-8 shrink-0 items-center gap-1 border-b border-border/60 pl-3 pr-1">
      <h3 className="min-w-0 flex-1 truncate text-tiny text-foreground">{t("preview.settingsTitle")}</h3>
      <button type="button" aria-label={t("preview.close")} onClick={onClose}
        className="flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45">
        <X className="size-3" aria-hidden="true" />
      </button>
    </div>
    <div className="shrink-0 border-b border-border/60 p-1">
      <FileSheetSettingsSection title={t("preview.orbit")} enabled={orbit} onEnabledChange={onOrbitChange}>
        <FileSheetSettingRow label={t("preview.speed")}>
          <Select value={String(speed)} onValueChange={value => onSpeedChange(Number(value))}>
            <SelectTrigger aria-label={t("preview.orbitSpeed")} size="sm" className={cn(FILE_SHEET_SELECT_TRIGGER_CLASSES, "!h-6 ml-auto w-fit max-w-full")}><SelectValue /></SelectTrigger>
            <SelectContent>{speeds.map(value => <SelectItem key={value} value={String(value)}>{value}×</SelectItem>)}</SelectContent>
          </Select>
        </FileSheetSettingRow>
      </FileSheetSettingsSection>
    </div>
    <div className="flex min-h-0 flex-1 flex-col">{render}</div>
  </div>;
}
