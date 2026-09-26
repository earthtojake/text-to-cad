import { viewerLoadingState } from "../status/loadingState.js";

/**
 * What the shell asks the status kit about one document load, in one pure
 * function: the loading presentation over the viewport.
 *
 * The shell knows four things about a load — whether the renderer is busy, what
 * it has on screen, what failed and how far it has got. A renderer whose
 * document can be EDITED or PREVIEWED while it is open knows more, and says so in
 * `load`. Every one of those is optional: leave them out and this is exactly the
 * report a renderer with a plain download gets.
 *
 * @param {object} options
 * @param {{ busy?: boolean, updating?: boolean, progress?: object | null,
 *   editPending?: boolean, currentPreview?: boolean, finding?: boolean }} options.load
 *   The renderer's document load. `editPending`: work of the person's own is queued or running that
 *   has not reached the scene yet. `currentPreview`: what is on screen IS that work's result, so the
 *   wait is over even though the write is not. `finding`: the file itself is still being located.
 * @param {object | null} options.alert  The blocking/failing alert the shell resolved.
 * @param {boolean} options.busy  The shell's own reasons to be busy, beside `load.busy`.
 * @param {boolean} options.previousView  A complete view of this file is already on screen.
 * @param {boolean} options.preparing
 */
export function shellLoadReport({ load, alert = null, busy = false, previousView = false, preparing = false }) {
  return viewerLoadingState({
    busy: Boolean(load.busy) || Boolean(load.updating) || busy,
    editPending: load.editPending === true,
    currentPreview: load.currentPreview === true,
    finding: load.finding === true,
    previousView,
    error: alert,
    progress: load.progress || null,
    preparing
  });
}
