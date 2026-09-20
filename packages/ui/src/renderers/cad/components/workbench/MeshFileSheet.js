import FileSheet from "../../../kit/inspector/FileSheet.js";
import FileSheetTabbedSurface from "../../../kit/inspector/FileSheetTabbedSurface.js";

// The mesh Inspector: Display, plus whatever settings tabs the caller adds (DXF reuses
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
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
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
        sections={settingsTabs}
        openSectionIds={openSectionIds}
        onOpenSectionIdsChange={onOpenSectionIdsChange}
      />
    </FileSheet>
  );
}
