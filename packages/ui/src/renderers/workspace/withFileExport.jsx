import { useMemo } from "react";
import { useExportView } from "../../export/context.js";
import { useViewerHost } from "../../host/context.js";
import { useWorkspaceDocument } from "./useWorkspaceDocument.js";

/**
 * A KiCad file's renderer (a board's, a schematic's) with Export: the file on screen published as the file menu's export source
 * (`useExportView`), so its Export submenu offers KiCad's files of it (`export/formats.ts`). The source
 * is the file's path and the catalog's hash of the bytes on screen, its revision; the server refuses a
 * file that has changed since. Beside the renderer, not in it, so the view stays its own.
 *
 * @template P
 * @param {import("react").ComponentType<P>} Board
 */
export function withFileExport(Board) {
  function WithExport(props) {
    const { data, ...view } = props;
    const workspace = useWorkspaceDocument({ view, data });
    const host = useViewerHost();
    const revision = String(workspace.entry?.hash || "");
    const exportView = useMemo(() => revision && workspace.modelKey && !host.environment.compact ? {
      doc: workspace.modelKey, revision, file: view.file.path, name: view.file.name
    } : null, [revision, workspace.modelKey, host.environment.compact, view.file.path, view.file.name]);
    useExportView(exportView);
    return <Board {...props} />;
  }
  return WithExport;
}
