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
 * Joints' Pose, the first row of its body, over the joints (under the motion and its hairline, where the tab holds
 * one): a panel settings row (`PanelSelectRow`, `panelRows.jsx`, the panel's 28px) — its label, **Position**, on the
 * panel's 16px line, and the pose in hand as a dropdown half the row wide (wider only where its value needs it), ending
 * on the right 16px line, as every settings row's control does ("Custom" while the joints are set by hand):
 * Default first where the section can reset, then the named poses. Reset, the way back to the default
 * pose, is the tab's ONE Reset, at its bottom right in its actions row (`KinematicsResetRow`). Nothing where there
 * is neither to choose. Never disabled: a motion holding the model is let go of by a choice here (one motion at a time).
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
 * the way back to the default pose, off while the model is there. Where the tab holds its mechanism's motion too
 * (`routine`: `{ away, reset }`), the ONE Reset puts back both — the motion to its start, the joints to their default —
 * and is on while either is off it.
 */
export function KinematicsResetRow({ activeValue, onReset, routine = null }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  if (!onReset) return null;
  const posed = activeValue !== DEFAULT_POSE_VALUE;
  const changed = posed || Boolean(routine?.away);
  const reset = () => {
    if (routine?.away) routine.reset();
    if (posed || !routine) { usage.used("position_reset"); onReset(); }
  };
  return <PanelActions data-pose-actions="">
    {/* Its word Params' Reset's, its name the joints' ("Reset joints"). */}
    <Button type="button" variant="ghost" size="xs" className={PANEL_ACTION_CLASS} data-pose-reset="" aria-label={t("pose.reset")}
      disabled={!changed} onClick={reset}>
      {t("parameters.reset")}
    </Button>
    {/* The tab's dot: on exactly while Reset is. */}
    <FlatPanelChanged on={changed} />
  </PanelActions>;
}
