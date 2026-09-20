import { MotionResetButton } from "../../../kit/inspector/kinematicsControls.jsx";
import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";

// The Kinematics tab: named poses and joint values. Animation is the Animate tool and its
// playbar, not an Inspector section, so a file with routines and no joints has no such tab.
// One host command still resets all motion, including pending playback and pose frames.
export function buildMotionControlsTab({ poseRuntime = null, animationRuntime = null, poseProps = {} } = {}) {
  const hasPosition = poseControlsHaveContent(poseRuntime, poseProps);
  if (!hasPosition) return null;
  const onReset = poseRuntime?.onResetMotion || animationRuntime?.resetModel || poseRuntime?.onResetParameters;
  return {
    id: FILE_SHEET_SECTION_IDS.KINEMATICS,
    title: "Kinematics",
    content: (
      <div>
        <PoseControlsSection {...poseProps} runtime={poseRuntime} />
        <MotionResetButton onReset={onReset} />
      </div>
    ),
  };
}
