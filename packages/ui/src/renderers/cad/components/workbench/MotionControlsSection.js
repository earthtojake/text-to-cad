import AnimationControlsSection, { animationControlsHaveContent } from "./AnimationControlsSection.js";
import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";

// One place to discover movement controls; each runtime still owns its own state.
// Animation comes first, followed by the independent position and preset controls.
export function buildMotionControlsTab({ poseRuntime = null, animationRuntime = null, poseProps = {} } = {}) {
  const hasAnimation = animationControlsHaveContent(animationRuntime);
  const hasPosition = poseControlsHaveContent(poseRuntime, poseProps);
  if (!hasAnimation && !hasPosition) return null;
  return {
    id: FILE_SHEET_SECTION_IDS.MOTION,
    title: "Motion",
    content: (
      <div className="py-2">
        {hasAnimation ? <AnimationControlsSection runtime={animationRuntime} /> : null}
        {hasPosition ? <PoseControlsSection {...poseProps} runtime={poseRuntime} /> : null}
      </div>
    ),
  };
}
