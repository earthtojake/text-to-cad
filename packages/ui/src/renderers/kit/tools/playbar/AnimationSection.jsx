import { useEffect } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import ToolPanel from "../ToolPanel.jsx";
import { TOP_STRIP_BUTTON_CLASS } from "../stripTouch.js";
import { PanelSelectRow, PanelSwitchRow } from "../../inspector/panelRows.jsx";
import { AnimationTimeControl, PLAYBACK_SPEEDS, animationControlsHaveContent, playbarWords } from "./AnimationTimeControl.js";
import { FlatPanelChanged } from "../../shell/FlatPanel.jsx";

/**
 * The tools view's routines, a tab of the view's panel, **Animation** (`ToolPanel`, `kit/shell/FlatPanel.jsx`), the last,
 * for a file the tools view plays clips for (its renderer's routines; none: no tab).
 * It is roomier than a playbar could be, in the panel's settings-row patterns (`settings-ui.md`):
 *
 * - **Clip**: the routine, a labelled dropdown row as Speed is (`PanelSelectRow`, `kit/inspector/panelRows.jsx`), always
 *   (one routine too), listing every routine; a choice plays it from its start. The tab's and the row's words are the
 *   routines' own, by `kind` (the renderer's: the shell passes it): an animation's are "Animation" and "Animation"; a
 *   mechanism's motion, an ISO 10303-105 `interpolated_configuration_sequence`, are "Motion" and "Sequence".
 * - **The transport**, a playbar's: Play/Pause, then **Reset** (each the strip's 28px tile), which puts the routine back
 *   at its start and the model at rest (`onRelease`), then the scrubber the rest of the row; no time readout (the time is the scrubber's value, read out to assistive
 *   technology). Its start is the rest pose: at 0 and not playing (scrubbed there, or paused there), the routine lets
 *   go of the model (`onRelease`), and the model is as built.
 * - **Speed**, **Loop** and **Autoplay**, the Playback settings menu's own items (`PlaybackMenu.jsx`) as rows: Speed a
 *   dropdown ("1×"); Loop and Autoplay switch rows, a label and its switch. The file's, kept in its view. One
 *   group of 28px rows 4px apart, every control's right edge on the panel's right 16px line.
 *
 * One motion at a time holds as it did on the playbar (`motionExclusion`, the renderer's): playing puts a pose
 * and the model's effects at rest, and a joint's edit or an effect puts the routine at rest. Leaving the tab or shutting the
 * panel leaves a playing routine playing (there is no other control for it on screen; the tab comes back to it).
 *
 * @param {{ runtime: object | null, kind?: "animation" | "motion", disabled?: boolean, autoplay: boolean, onAutoplayChange(value: boolean): void }} props
 *   `runtime`: the routine runtime (`AnimationTimeControl.js`), its presses counted by its owner (`RendererShell.jsx`).
 *   `kind`: "motion" for a mechanism's motions, else "animation".
 */
export default function AnimationSection(props) {
  return animationControlsHaveContent(props.runtime) ? <AnimationTab {...props} /> : null;
}

function AnimationTab({ runtime, kind = "animation", disabled = false, autoplay, onAutoplayChange }) {
  const { t } = useI18n();
  const motion = kind === "motion";
  const playing = runtime.playing === true;
  // At its start and not playing, the routine holds nothing: the model is at rest (a routine's first frame
  // need not be its rest pose: a motion that opens at a named state).
  const atStart = runtime.enabled === true && !playing && !(Number(runtime.elapsedSec) > 0);
  useEffect(() => { if (atStart) runtime.onRelease?.(); }, [atStart]);
  // Off its start (playing, or paused or stopped past it), Reset has something to put back.
  const away = runtime.enabled === true && (playing || Number(runtime.elapsedSec) > 0);
  const words = playbarWords(runtime, t);
  const clips = runtime.clips;
  const active = clips.find(clip => clip.id === runtime.activeClipId) || clips[0];
  // The scrubber's start is the rest pose: scrubbed there, not playing, the routine lets the model go.
  const scrubbed = { ...runtime, onScrub: value => {
    if (!playing && !(Number(value) > 0)) { runtime.onRelease?.(); return; }
    runtime.onScrub?.(value);
  } };
  // A routine chosen plays from its start (the shell's `playClip`, which counts it; else the routine's own steps).
  const playClip = id => {
    if (runtime.playClip) { runtime.playClip(id); return; }
    runtime.onClipSelect?.(id);
    runtime.onPlayToggle?.();
  };
  const speed = Number(runtime.speed) || 1;
  const speeds = PLAYBACK_SPEEDS.includes(speed) ? PLAYBACK_SPEEDS : [...PLAYBACK_SPEEDS, speed].sort((a, b) => a - b);
  return <ToolPanel id="animation" title={t(motion ? "animation.motionTab" : "animation.tab")} label={words.playback} fit="details">
    <div className="flex flex-col gap-1" data-animation-section="">
      {/* The routine: a labelled dropdown as Speed is, every routine listed (one too). */}
      <PanelSelectRow label={t(motion ? "animation.sequence" : "animation.clip")} value={active?.id} disabled={disabled} triggerLabel={`${words.list}: ${active?.label ?? ""}`}
        options={clips.map(clip => ({ value: clip.id, label: clip.label }))} onChange={id => playClip(id)}
        triggerProps={{ "data-animation-clip-menu": "" }} optionProps={option => ({ "data-animation-clip": option.value })} />
      {/* The transport: Play/Pause and Reset at its left (the strip's 28px tiles and icons), the scrubber the rest of the
          row; the time is the scrubber's own value, read out to assistive technology. Play's tile hangs out past the
          panel's inset by its own 6px, so its icon stands on the inset; the scrubber ends on the right one. */}
      <div className="-ml-1.5 flex h-7 min-w-0 items-center gap-1" data-animation-transport="">
        <ToolbarButton tooltip={false} disabled={disabled} label={playing ? words.pause : words.play} onClick={() => runtime.onPlayToggle?.()}
          className={TOP_STRIP_BUTTON_CLASS} data-animation-play="">
          {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        </ToolbarButton>
        {/* The tab's dot: on exactly while Reset is (Speed, Loop and Autoplay are preferences, never it). */}
        <FlatPanelChanged on={!(disabled || !away)} />
        <ToolbarButton tooltip={false} disabled={disabled || !away} label={t("animation.reset")} onClick={() => runtime.onRelease?.()}
          className={TOP_STRIP_BUTTON_CLASS} data-animation-reset="">
          <RotateCcw aria-hidden="true" />
        </ToolbarButton>
        <div className="ml-1 min-w-0 flex-1" data-animation-scrubber="">
          <AnimationTimeControl runtime={scrubbed} disabled={disabled} className="h-4 w-full" />
        </div>
      </div>
      {/* The playback settings, the Playback settings menu's own (`PlaybackMenu.jsx`): Speed a dropdown as Position is,
          Loop and Autoplay switches, a label and its switch. */}
      <PanelSelectRow label={t("playback.speed")} value={String(speed)} disabled={disabled} triggerLabel={`${t("playback.animationSpeed")}: ${speed}×`}
        options={speeds.map(value => ({ value: String(value), label: `${value}×` }))} onChange={value => runtime.onSpeedChange?.(Number(value))}
        triggerProps={{ "data-animation-speed": "" }} />
      <PanelSwitchRow label={t("playback.loop")} checked={runtime.loopEnabled !== false} disabled={disabled}
        onChange={on => runtime.onLoopToggle?.(on)} rowProps={{ "data-animation-loop": "" }} />
      <PanelSwitchRow label={t("playback.autoplay")} checked={autoplay === true} disabled={disabled}
        onChange={on => onAutoplayChange?.(on)} rowProps={{ "data-animation-autoplay": "" }} />
    </div>
  </ToolPanel>;
}
