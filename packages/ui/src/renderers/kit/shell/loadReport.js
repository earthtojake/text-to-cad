import { resolveFileStatus } from "../status/fileStatus.js";
import { resolveFileStatusAlert } from "../status/loadAlerts.js";
import { viewerLoadingState } from "../status/loadingState.js";

/**
 * Everything the shell asks the status kit about one document load, in one pure
 * function: the loading presentation, the chip beside the filename, and the
 * alert that chip opens.
 *
 * The shell knows four things about a load — whether the renderer is busy, what
 * it has on screen, what failed and how far it has got. A renderer whose
 * document can be EDITED or PREVIEWED while it is open, or whose view can be
 * degraded without failing, knows more, and says so in `load` and `fileStatus`.
 * Every one of those is optional: leave them out and this is exactly the report
 * a renderer with a plain download gets.
 *
 * @param {object} options
 * @param {{ busy?: boolean, updating?: boolean, progress?: object | null, alert?: object | null,
 *   warning?: object | null, editPending?: boolean, currentPreview?: boolean, finding?: boolean }} options.load
 *   The renderer's document load. `editPending`: work of the person's own is queued or running that
 *   has not reached the scene yet. `currentPreview`: what is on screen IS that work's result, so the
 *   wait is over even though the write is not. `finding`: the file itself is still being located.
 *   `warning`: something about this file could not be applied and the model survives it — it rides
 *   the badge and opens as an alert, and it is not a failed load.
 * @param {object} [options.fileStatus]  Extra fields for `resolveFileStatus`, merged OVER what the
 *   shell derives: `editingState`, `savedAs`, `showingPreview`, `qualityStatus`, and `hasGeometry`
 *   for a renderer whose scene can exist before its geometry is whole.
 * @param {boolean} options.hasFile
 * @param {object | null} options.alert  The blocking/failing alert the shell resolved.
 * @param {boolean} options.busy  The shell's own reasons to be busy, beside `load.busy`.
 * @param {boolean} options.previousView  A complete view of this file is already on screen.
 * @param {boolean} options.hasGeometry
 * @param {boolean} options.renderMode
 * @param {boolean} options.preparing
 */
export function shellLoadReport({ load, fileStatus = {}, hasFile, alert = null, busy = false,
  previousView = false, hasGeometry = false, renderMode = false, preparing = false }) {
  const warning = load.warning || null;
  const loading = viewerLoadingState({
    busy: Boolean(load.busy) || Boolean(load.updating) || busy,
    editPending: load.editPending === true,
    currentPreview: load.currentPreview === true,
    finding: load.finding === true,
    previousView,
    error: alert,
    progress: load.progress || null,
    preparing
  });
  const status = resolveFileStatus({
    hasFile, error: alert || warning, opening: loading.opening, updating: loading.updating,
    loadingProgress: loading.progress, renderMode, hasGeometry,
    ...fileStatus
  });
  return { loading, fileStatus: status, fileStatusAlert: resolveFileStatusAlert(status, alert, warning) };
}
