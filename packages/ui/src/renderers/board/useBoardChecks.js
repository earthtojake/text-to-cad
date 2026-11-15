/**
 * The board's design rule check (`client.boardDrc`, `GET /api/v1/documents/kicad_pcb/<id>/drc`): KiCad's
 * DRC of the saved board, which the server runs off the request and keeps by the board's bytes, read as
 * the view reads it (`@cad/core/lib/board2d/boardChecks.js`: the verdict, the counts, each finding's
 * place on the page and the references of what it is between). Asked again on every revision of the
 * board — while it is, the view says it is checking and shows nothing of the revision before — and when
 * the window takes the focus back (its rules or its schematic edited meanwhile: the server's key holds
 * them), which changes nothing on screen unless the answer differs.
 *
 * A check that could not be made — no KiCad on this computer, a board KiCad refused, a server that
 * stopped answering — is `notChecked` with the reason, quietly: the board is still the board, and
 * nothing here raises the view's alert. Null where the host's client has no such route.
 *
 * Importing this module has no environmental effects.
 */
import { useEffect, useMemo, useState } from "react";
import { boardChecks } from "@cad/core/lib/board2d/boardChecks.js";

const CHECKING = Object.freeze({ state: "checking", verdict: null, reason: "", counts: Object.freeze({ errors: 0, unconnected: 0, warnings: 0, excluded: 0 }),
  failing: 0, findings: Object.freeze([]), notes: Object.freeze([]) });
// Why a request failed, in the server's own words where it gave any (`ViewerRequestError`'s `failure.detail`).
const reasonOf = error => String(error?.failure?.detail || error?.message || error || "");

/**
 * @param {{ client: import("@cad/core/client").CadWorkspaceService, file: string, revision?: string,
 *   index: ReturnType<typeof import("@cad/core/lib/board2d/boardIndex.js").createBoardIndex> | null }} options
 * @returns {(ReturnType<typeof boardChecks> | typeof CHECKING) | null}
 */
export function useBoardChecks({ client, file, revision = "", index }) {
  const offered = Boolean(index) && Boolean(file) && typeof client?.boardDrc === "function";
  const key = JSON.stringify([file, revision]);
  // The answer for `key`: the route's payload, or why there is none.
  const [answer, setAnswer] = useState(null);
  const [focus, setFocus] = useState(0);
  useEffect(() => {
    if (!offered) return undefined;
    const regained = () => setFocus(count => count + 1);
    window.addEventListener("focus", regained);
    return () => window.removeEventListener("focus", regained);
  }, [offered]);
  useEffect(() => {
    if (!offered) return undefined;
    const controller = new AbortController();
    const settle = next => setAnswer(current => (current && JSON.stringify(current) === JSON.stringify(next) ? current : next));
    client.boardDrc(file, { signal: controller.signal })
      .then(payload => settle({ key, payload }))
      .catch(error => { if (!controller.signal.aborted) settle({ key, failed: reasonOf(error) }); });
    return () => controller.abort();
  }, [client, file, key, focus, offered]);
  const current = answer?.key === key ? answer : null;
  return useMemo(() => {
    if (!offered) return null;
    if (!current) return CHECKING;
    return current.payload !== undefined ? boardChecks(current.payload, index) : { ...boardChecks(null), reason: current.failed };
  }, [offered, current, index]);
}
