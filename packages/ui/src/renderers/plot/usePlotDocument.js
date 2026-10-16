import { useMemo } from "react";
import { createBoardIndex } from "@text-to-cad/core/lib/board2d/boardIndex.js";
import { plotLoadAlert, usePlotPayload } from "./usePlotPayload.js";
import { plotKindForPath, plotWords } from "./plotWords.js";

/**
 * The document on screen (`useRobotDocument.js` is a robot's): the plot (`usePlotPayload`), what
 * kind of document it is, said once — `"board"`, from the payload, and from the file's name until
 * it has arrived — the sentences that kind is spoken of in, its index (the board's parts, pads and
 * nets, when the payload carries one: with it, the board has the tools a person points with), and
 * the load's alert.
 *
 * @param {{ workspace: ReturnType<typeof import("../workspace/useWorkspaceDocument.js").useWorkspaceDocument>, path: string }} options
 */
export function usePlotDocument({ workspace, path }) {
  const file = workspace.entry?.file || path;
  const payload = usePlotPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const { plot } = payload;
  const kind = plot?.layout.kind || plotKindForPath(path);
  const words = plotWords(kind);
  const sheet = plot?.layout.sheets[0] ?? null;
  const board = plot?.board ?? plot?.layout.board ?? null;
  const index = useMemo(() => (board && sheet ? createBoardIndex(board, { x: sheet.x, y: sheet.y }) : null), [board, sheet]);
  // A board drawn layer by layer can be seen from either side, with any of its layers: its Display.
  const layered = kind === "board" && Array.isArray(sheet?.layers) && sheet.layers.length > 0;

  // With a plot on screen, a failure to read the file again leaves that plot to use.
  const shown = Boolean(plot);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: words.openFailed,
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = plotLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} ${words.remains}` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown, words]);

  return {
    file, plot, kind, words, index, sheet, layered, shown, loading: payload.loading,
    /** What the shell's frame reads of the load. */
    load: { shown, busy: payload.loading, updating: payload.updating, alert, reading: words.reading, updateStatus: words.updateStatus },
  };
}
