// The Studio tab's descriptor. The editor itself is a lazy chunk
// (RenderSettingsContent.js): only Render mode can open it, and Render's mode
// switch warms the chunk, so the fallback below is what a cold cache sees
// rather than what a mode switch shows.
import { lazy, Suspense } from "react";

import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";
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

export function buildRenderSettingsTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.RENDER,
    title: "Studio",
    content: <RenderSettingsPanel {...props} />
  };
}
