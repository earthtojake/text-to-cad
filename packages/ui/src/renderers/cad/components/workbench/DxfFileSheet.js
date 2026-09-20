import FileSheet from "../../../kit/inspector/FileSheet.js";
import FileSheetTabbedSurface from "../../../kit/inspector/FileSheetTabbedSurface.js";

// A drawing's Inspector: the tabs its caller builds (Material, Bends, Layers, Display),
// in the one tab strip every Inspector has.
export default function DxfFileSheet({
  headerActions = null,
  open,
  title = "DXF",
  isDesktop,
  width,
  onOpenChange,
  onStartResize,
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
