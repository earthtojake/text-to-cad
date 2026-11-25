import { useI18n } from "@cad/ui/i18n";
import { SettingsCard } from "../view-settings/SettingsCard.jsx";
import { previewRenderSections, previewRenderState } from "../view-settings/PreviewRenderSettings.jsx";
import { ORBIT_SPEEDS } from "../tools/PlaybackMenu.jsx";

/**
 * Preview's **Settings**, a settings card (`SettingsCard.jsx`, the Display card's sibling) docked under Preview's bar
 * at the view's right edge (closed as Preview opens; its settings button and this X put it away): **Orbit** — the
 * camera turning about the model, a switch heading its section (Preview's own, off each time it opens), and its
 * **Speed** under it while it turns (the file's) — then Render's own settings (`render`, `PreviewRenderSettings.jsx`:
 * part colours, lighting, background, floor), and Reset, which puts Render's settings back.
 *
 * @param {{ orbit: boolean, onOrbitChange(value: boolean): void, speed: number, onSpeedChange(value: number): void,
 *   onClose(): void, render: object }} props  `render`: Render's settings and their writes (`previewRenderSections`).
 */
export default function PreviewSettings({ orbit, onOrbitChange, speed, onSpeedChange, onClose, render }) {
  const { t } = useI18n();
  const speeds = ORBIT_SPEEDS.includes(speed) ? ORBIT_SPEEDS : [...ORBIT_SPEEDS, speed].sort((a, b) => a - b);
  const index = Math.max(0, speeds.indexOf(speed));
  const orbitRows = [
    { kind: "switch", head: true, id: "orbit", label: t("preview.orbit"), value: orbit, onChange: onOrbitChange },
    // Speed's stops are the playbar's speeds (and the file's own, where it has another): the slider steps through them.
    orbit ? { kind: "slider", id: "orbit-speed", label: t("preview.speed"), name: t("preview.orbitSpeed"), value: index, min: 0, max: speeds.length - 1,
      step: 1, text: `${speeds[index]}×`, valueLabel: t("render.valueOf", { name: t("preview.orbitSpeed") }),
      onChange: next => { const value = speeds[Math.round(next)]; if (value !== undefined && value !== speed) onSpeedChange(value); },
      onCommit: draft => { const value = Number.parseFloat(draft); if (speeds.includes(value) && value !== speed) onSpeedChange(value); } } : null
  ];
  return <SettingsCard title={t("preview.settingsTitle")} closeLabel={t("preview.close")} onClose={onClose} aria-label={t("preview.settings")}
    data-preview-settings-panel="" sections={[orbitRows, ...previewRenderSections(render, t)]}
    onReset={render.onReset} resetLabel={t("settings.reset")} resetDisabled={!previewRenderState(render).changed} resetProps={{ "data-preview-settings-reset": "" }} />;
}
