import FileSheet from "../../../kit/inspector/FileSheet.js";
import FileSheetTabbedSurface from "../../../kit/inspector/FileSheetTabbedSurface.js";
import { buildMotionControlsTab } from "./MotionControlsSection.js";

// The mesh Inspector: View, plus whatever settings tabs the caller adds (DXF reuses
// this sheet). Measurements are the Measure tool's panel, not an Inspector tab.
export default function MeshFileSheet({
  headerActions = null,
  open,
  kind = "mesh",
  title = "Mesh",
  isDesktop,
  width,
  selectedEntry = null,
  onOpenChange,
  onStartResize,
  viewerServerInfo = null,
  suppressDynamicMetadataStatus = false,
  settingsTabs = [],
  animationRuntime = null,
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
  const motionTab = buildMotionControlsTab({ animationRuntime });
  const sections = [
    ...(motionTab ? [motionTab] : []),
    ...settingsTabs
  ];

  return (
    <FileSheet
      open={open}
      title={title}
      isDesktop={isDesktop}
      width={width}
      onOpenChange={onOpenChange}
      onStartResize={onStartResize}
      scrollBody={false}
    >
      <FileSheetTabbedSurface headerActions={headerActions}
        sections={sections}
        openSectionIds={openSectionIds}
        onOpenSectionIdsChange={onOpenSectionIdsChange}
      />
    </FileSheet>
  );
}
