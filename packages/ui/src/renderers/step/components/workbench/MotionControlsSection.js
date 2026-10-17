import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";
import { MotionResetButton } from "../../../kit/inspector/kinematicsControls.jsx";

// The Position panel for STEP (the tool stack's, shown while the Position tool is up): its
// named poses, its joint values and the Reset that puts them back. Animation is a tool of its
// own (and preview's playbar), not a section, so a file with routines and no joints has no
// Position at all. One host command still resets all motion, including pending playback and pose frames.
export function buildPositionSection({ poseRuntime = null } = {}) {
  if (!poseControlsHaveContent(poseRuntime)) return null;
  const onReset = poseRuntime?.onResetMotion || poseRuntime?.onResetParameters;
  return {
    id: "position",
    title: "Position",
    // Reset is the panel heading's, beside its title.
    actions: onReset ? <MotionResetButton onReset={onReset} /> : null,
    content: (
      <div className="space-y-1.5 pb-1.5 pt-0.5">
        <PoseControlsSection runtime={poseRuntime} />
      </div>
    ),
  };
}
