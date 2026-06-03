import {
  Accordion
} from "../ui/accordion";
import FileSheet from "./FileSheet";
import FileMetadataSection from "./FileMetadataSection";
import FileStatusSection from "./FileStatusSection";
import ImplicitGraphicsSection from "./ImplicitGraphicsSection";
import ParameterControlsSection from "./ParameterControlsSection";

export default function ImplicitFileSheet({
  open,
  title = "Implicit CAD",
  isDesktop,
  width,
  selectedEntry = null,
  onOpenChange,
  onStartResize,
  parameterRuntime = null,
  graphicsRuntime = null,
  fileDownloadAvailable = false,
  viewerServerInfo = null,
  localFileOpenAvailable = false,
  fileAccessBusyKey = "",
  onOpenFileAsset,
  suppressDynamicMetadataStatus = false,
  statusItems = [],
  themeSections = null,
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
    >
      <Accordion
        type="multiple"
        value={openSectionIds}
        onValueChange={onOpenSectionIdsChange}
        className="text-sm"
      >
        <FileStatusSection items={statusItems} />
        <ParameterControlsSection
          runtime={parameterRuntime}
          label="implicit parameter"
          loadingLabel="Loading implicit parameters..."
          noParametersLabel="No implicit parameters."
          hideWhenEmpty
          animationAriaLabel="Implicit animation"
          copyTitle="Copy implicit parameter JSON"
          pasteTitle="Paste implicit parameter JSON"
        />
        <ImplicitGraphicsSection runtime={graphicsRuntime} />
        {themeSections}
        <FileMetadataSection
          entry={selectedEntry}
          fileDownloadAvailable={fileDownloadAvailable}
          viewerServerInfo={viewerServerInfo}
          localFileOpenAvailable={localFileOpenAvailable}
          fileAccessBusyKey={fileAccessBusyKey}
          onOpenFileAsset={onOpenFileAsset}
          suppressDynamicStatus={suppressDynamicMetadataStatus}
        />
      </Accordion>
    </FileSheet>
  );
}
