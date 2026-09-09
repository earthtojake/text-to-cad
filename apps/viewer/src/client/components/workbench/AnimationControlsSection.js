import { Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import {
  ANIMATION_SPEED_MAX,
  ANIMATION_SPEED_MIN
} from "cadgen-js/common/animationClock";
import { useAnimationClock } from "@/workbench/animationClockStore";
import { animationClipOptions } from "@/workbench/animationClipOptions";
import { Button } from "../ui/button";
import { Slider } from "../ui/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetBooleanToggle,
  FileSheetButtonRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";

// The ANIMATION tab: pick a clip, play it, scrub it.
//
// The other half of the pose/animation split. Clips are choreography compiled
// from the sidecar's copied .anim.js text and are pure functions of t, which is
// why scrub and pause need nothing but a number. This section never reads a
// DOF, a mate or a preset.

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;

function formatSeconds(value) {
  const numericValue = Math.max(Number(value) || 0, 0);
  return `${numericValue.toFixed(numericValue >= 10 ? 1 : 2)}s`;
}

function formatSpeed(value) {
  const numericValue = Number(value);
  return `${(Number.isFinite(numericValue) ? numericValue : 1).toFixed(1)}x`;
}

// The time slider tracks the LIVE clock while playing: the elapsed time on the
// runtime snapshot only moves when playback stops, because a playing clip
// publishes through the clock store instead of React state.
function AnimationTimeControl({ playing, elapsedSec, duration, enabled, onScrub }) {
  const liveElapsedSec = useAnimationClock();
  const rawElapsedSec = playing ? liveElapsedSec : elapsedSec;
  const value = Math.min(Math.max(Number(rawElapsedSec) || 0, 0), duration);
  return (
    <FileSheetSliderField
      label="Time"
      value={formatSeconds(value)}
      onValueCommit={(nextValue) => {
        onScrub?.(parseFileSheetNumberInput(nextValue, {
          fallback: value,
          min: 0,
          max: duration
        }));
      }}
      valueInputProps={{
        disabled: !enabled,
        ariaLabel: "Animation time value"
      }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[value]}
        min={0}
        max={duration}
        step={0.01}
        onValueChange={(nextValue) => onScrub?.(nextValue?.[0] ?? 0)}
        disabled={!enabled}
        aria-label="Animation time"
      />
    </FileSheetSliderField>
  );
}

export default function AnimationControlsSection({ runtime = null }) {
  const clips = Array.isArray(runtime?.clips) ? runtime.clips : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const activeClip = clips.find((clip) => clip.id === runtime?.activeClipId) || null;
  const duration = Math.max(Number(activeClip?.duration) || 1, 0.001);
  // The section's gate: with animation off the evaluator never runs and the
  // model shows whatever the Pose tab set. A clip is always selected, so this
  // switch — not a picker entry — is how the transport is idled.
  const enabled = runtime?.enabled !== false;
  if (!animationControlsHaveContent(runtime)) {
    return null;
  }

  return (
    <div className="py-2">
      {status === "loading" ? (
        <FileSheetStatusText className="py-2">Loading animation...</FileSheetStatusText>
      ) : null}
      {error ? (
        <FileSheetStatusText tone="error" className="py-2">{error}</FileSheetStatusText>
      ) : null}

      {clips.length ? (
        // "Animation" names the system this group drives, the way the Kinematics
        // tab's section does. It does not collide with any row inside it
        // (settings-ui.md forbids a group sharing a name with its own rows, and
        // the rows here are Clip, Loop, Time and Speed).
        <FileSheetSubsection
          title="Animation"
          // The transport gate rides this heading on the shared right-edge control
          // axis, exactly as the Kinematics tab's mate gate does.
          trailing={(
            <FileSheetBooleanToggle
              checked={enabled}
              onCheckedChange={(checked) => runtime?.onEnabledChange?.(checked)}
              ariaLabel="Enable animation"
            />
          )}
        >
          {/* The section's primary control: which clip is selected reframes the
              transport and the time/speed rows beneath it. It lists the model's
              authored clips and nothing else -- the idle state is the gate switch
              above, not an entry here -- and the gate disables it with every
              other row it owns, exactly as the Kinematics tab's gate disables the
              DOFs and presets it owns. A gate turns its whole feature off; one
              live row under an off switch reads as a control that still does
              something, and this one silently rewinds the clock. */}
          <FileSheetSelectRow
            stacked
            label="Clip"
            value={activeClip?.id || ""}
            onValueChange={(nextValue) => runtime?.onClipSelect?.(nextValue)}
            disabled={!enabled}
            ariaLabel="Animation clip"
            options={animationClipOptions(clips)}
          />
          {/* "Restart" is deliberately not called "Reset": it returns playback to
              zero, where the Pose tab's Reset returns the DOFs to their defaults.
              Play is the ONE control the gate does not disable, here and on the
              toolbar: pressing it means "run this clip", so it opens the gate.
              The toolbar's copy sits outside this tab and has no way to say that
              animation is switched off, and a Play that did nothing would be the
              worse failure -- so both buttons behave the same way. */}
          <FileSheetButtonRow columns={2}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(compactButtonClasses, "justify-center")}
              onClick={() => runtime?.onPlayToggle?.()}
              aria-label={`${runtime?.playing ? "Pause" : "Play"} animation`}
              title={`${runtime?.playing ? "Pause" : "Play"} animation`}
            >
              {runtime?.playing ? (
                <Pause className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              ) : (
                <Play className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              )}
              <span>{runtime?.playing ? "Pause" : "Play"}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(compactButtonClasses, "justify-center")}
              onClick={() => runtime?.onRestart?.()}
              disabled={!enabled}
              aria-label="Restart animation"
              title="Restart"
            >
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>Restart</span>
            </Button>
          </FileSheetButtonRow>
          <FileSheetToggleRow
            label="Loop"
            checked={runtime?.loopEnabled !== false}
            onCheckedChange={(checked) => runtime?.onLoopToggle?.(checked)}
            disabled={!enabled}
            ariaLabel="Loop animation playback"
          />
          <AnimationTimeControl
            playing={runtime?.playing === true}
            elapsedSec={runtime?.elapsedSec}
            duration={duration}
            enabled={enabled}
            onScrub={runtime?.onScrub}
          />
          <FileSheetSliderField
            label="Speed"
            value={formatSpeed(runtime?.speed)}
            onValueCommit={(nextValue) => {
              runtime?.onSpeedChange?.(parseFileSheetNumberInput(nextValue, {
                fallback: runtime?.speed || 1,
                min: ANIMATION_SPEED_MIN,
                max: ANIMATION_SPEED_MAX
              }));
            }}
            valueInputProps={{
              disabled: !enabled,
              ariaLabel: "Animation speed value"
            }}
          >
            <Slider
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[Number(runtime?.speed) || 1]}
              min={ANIMATION_SPEED_MIN}
              max={ANIMATION_SPEED_MAX}
              step={0.1}
              onValueChange={(nextValue) => runtime?.onSpeedChange?.(nextValue?.[0] ?? 1)}
              disabled={!enabled}
              aria-label="Animation speed"
            />
          </FileSheetSliderField>
        </FileSheetSubsection>
      ) : null}
    </div>
  );
}

export function animationControlsHaveContent(runtime) {
  const clips = Array.isArray(runtime?.clips) ? runtime.clips : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  return Boolean(clips.length || status === "loading" || error);
}

export function buildAnimationControlsTab(props = {}) {
  if (!animationControlsHaveContent(props.runtime)) {
    return null;
  }
  return {
    id: props.value || "animation",
    title: props.title || "Animation",
    content: <AnimationControlsSection {...props} />
  };
}
