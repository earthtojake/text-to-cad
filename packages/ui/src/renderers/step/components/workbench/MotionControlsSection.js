import { MotionResetButton } from "../../../kit/inspector/kinematicsControls.jsx";
import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";

// The Position section of a STEP's panel: its named poses, its joint values and the Reset
// that puts them back, in one section. Animation is the Animate tool and its playbar, not
// a section, so a file with routines and no joints has no Position at all. One host
// command still resets all motion, including pending playback and pose frames.
export function buildPositionSection({ poseRuntime = null, animationRuntime = null, poseProps = {} } = {}) {
  if (!poseControlsHaveContent(poseRuntime, poseProps)) return null;
  const onReset = poseRuntime?.onResetMotion || animationRuntime?.resetModel || poseRuntime?.onResetParameters;
  return {
    id: "position",
    title: "Position",
    content: (
      <div className="space-y-1">
        <PoseControlsSection {...poseProps} runtime={poseRuntime} />
        <MotionResetButton onReset={onReset} />
      </div>
    ),
  };
}
