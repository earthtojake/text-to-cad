import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";

// The Position panel for STEP (the tool stack's, shown while the Position tool is up): its
// named poses, its joint values and the Reset that puts them back. Animation is the Animate
// tool and its playbar, not a section, so a file with routines and no joints has no Position
// at all. One host command still resets all motion, including pending playback and pose frames.
export function buildPositionSection({ poseRuntime = null, animationRuntime = null, poseProps = {} } = {}) {
  if (!poseControlsHaveContent(poseRuntime, poseProps)) return null;
  const onReset = poseRuntime?.onResetMotion || animationRuntime?.resetModel || poseRuntime?.onResetParameters;
  return {
    id: "position",
    title: "Position",
    content: (
      <div className="space-y-2 px-1 py-2">
        <PoseControlsSection {...poseProps} runtime={poseRuntime} onReset={onReset} />
      </div>
    ),
  };
}
