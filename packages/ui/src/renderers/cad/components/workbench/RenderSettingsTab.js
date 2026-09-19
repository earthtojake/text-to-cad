// The View tab's render-only controls. The editor itself is a lazy chunk
// (RenderSettingsContent.js), so ordinary View settings never fetch it.
import { lazy, Suspense } from "react";

import { importRenderSettingsContent } from "../../render/renderStudioChunk.js";
import { FileSheetLoadingBody } from "./FileSheet.js";

const RenderSettingsContent = lazy(importRenderSettingsContent);

export function RenderSettingsPanel(props) {
  return (
    <Suspense fallback={<FileSheetLoadingBody>Loading studio settings...</FileSheetLoadingBody>}>
      <RenderSettingsContent {...props} />
    </Suspense>
  );
}
