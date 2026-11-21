import { Button } from "@cad/ui/primitives/button";
import { PanelSelectRow } from "./panelRows.jsx";
import { PANEL_ACTION_CLASS, PanelActions } from "./PanelActions.jsx";
import { useControlUsage } from "../../../usage/controls.js";
import { useI18n } from "@cad/ui/i18n";
import { FlatPanelChanged } from "../shell/FlatPanel.jsx";

export const NO_PRESET_VALUE = "__none__";
export const DEFAULT_POSE_VALUE = "__default__";

export function positionValuesAreDefault(values, defaults) {
  return Object.entries(defaults || {}).every(([key, value]) => {
    const current = values?.[key] ?? value;
    return typeof value === "number" && typeof current === "number"
      ? Math.abs(current - value) <= 1e-6 : current === value;
  });
}

/**
 * Joints' Pose, the first row of its body, over the joints: a settings row (`FileSheetSettingRow`'s
 * shape, at the panel's 28px) — its label, **Position**, in the 4rem column on the 16px line, and the pose in
 * hand as a dropdown as wide as its value (6rem at least, the row's rest at most), at the row's right end on the
 * right 16px line, as a settings row's control is ("Custom" while the joints are set by hand):
 * Default first where the section can reset, then the named poses. Reset, the way back to the default
 * pose, is the tab's actions row, last (`KinematicsResetRow`). Nothing where there is neither to
 * choose. Never disabled: a motion holding the model is let go of by a choice here (one motion at a time).
 */
export function KinematicsPoseRow({ poses = [], activeValue, onSelect, onReset }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  if (!poses.length && !onReset) return null;
  const reset = () => { usage.used("position_reset"); onReset?.(); };
  const options = [...(onReset ? [{ value: DEFAULT_POSE_VALUE, label: t("pose.default") }] : []), ...poses];
  const active = options.find(pose => pose.value === activeValue);
  const label = active?.label || t("pose.custom");
  return <PanelSelectRow label={t("pose.label")} value={active?.value || NO_PRESET_VALUE} options={options} fallback={t("pose.custom")}
    triggerLabel={t("pose.current", { pose: label })} className="mb-2" rowProps={{ "data-pose-row": "" }} labelProps={{ "data-pose-label": "" }}
    triggerProps={{ "data-pose-menu": "" }}
    onChange={value => { if (value === DEFAULT_POSE_VALUE) { reset(); return; } usage.used("position_preset"); onSelect?.(value); }} />;
}

/**
 * Joints' actions row, last in the tab, where Params has its Reset and Save (`PanelActions`): Reset alone,
 * the way back to the default pose, off while the model is there.
 */
export function KinematicsResetRow({ activeValue, onReset }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  if (!onReset) return null;
  return <PanelActions data-pose-actions="">
    {/* Its word Params' Reset's, its name the joints' ("Reset joints"). */}
    <Button type="button" variant="ghost" size="xs" className={PANEL_ACTION_CLASS} data-pose-reset="" aria-label={t("pose.reset")}
      disabled={activeValue === DEFAULT_POSE_VALUE} onClick={() => { usage.used("position_reset"); onReset(); }}>
      {t("parameters.reset")}
    </Button>
    {/* The tab's dot: on exactly while Reset is. */}
    <FlatPanelChanged on={activeValue !== DEFAULT_POSE_VALUE} />
  </PanelActions>;
}
