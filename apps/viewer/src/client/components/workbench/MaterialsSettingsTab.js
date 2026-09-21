// The Materials tab's descriptor. The editor itself is a lazy chunk
// (MaterialsSettingsContent.js) because nothing outside Render mode can open
// it; this module stays in the initial bundle so the tab strip can be built
// without paying for the panel. Render's mode switch warms both halves, so the
// fallback below is what a cold cache sees, not what a mode switch shows.
import { lazy, Suspense } from "react";

import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import { importMaterialsSettingsContent } from "@/render/renderStudioChunk";
import { FileSheetLoadingBody } from "./FileSheet";

const MaterialsSettingsContent = lazy(importMaterialsSettingsContent);

export function MaterialsSettingsPanel(props) {
  return (
    <Suspense fallback={<FileSheetLoadingBody>Loading materials...</FileSheetLoadingBody>}>
      <MaterialsSettingsContent {...props} />
    </Suspense>
  );
}

export function buildMaterialsSettingsTab(props = {}) {
  // `enabled` is sourceMaterialsPanelEnabled's answer, decided once by the
  // workspace for both the tab strip and this tab. Do not re-derive it here.
  if (!props.enabled) return null;
  return {
    id: FILE_SHEET_SECTION_IDS.MATERIALS,
    title: "Materials",
    content: <MaterialsSettingsPanel {...props} />
  };
}
