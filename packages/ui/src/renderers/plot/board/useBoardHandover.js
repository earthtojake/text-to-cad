import { useCallback, useEffect, useMemo, useRef } from "react";
import { buildBoardRefToken, parseBoardRefSelector, splitBoardRefSelectors } from "@text-to-cad/core/lib/boardRefs.js";
import { findingCopyText } from "./boardFacts.js";

/**
 * What a board or a schematic hands over, in board references (`#U3`, `#U3.9`, `#net:VIN`) that the
 * agent resolves with `cadgen.pcb.read_board` / `read_schematic`: the selection as Quick Edit's
 * references (with a chosen check's sentence as their `summary`), as the copy key's text, and as the
 * live controller's `select` and `clearSelection`; and the host's own request to select a reference.
 * A harness has none of it: the host's select is declined in its words, and its request consumed.
 * Selection only: nothing here edits a design.
 *
 * @param {object} options
 * @param {{ resource: object, commands: object, acknowledgeCommand?: (kind: string, key: unknown) => void }} options.workspace
 * @param {{ kind: string, index: object | null, words: object, loading: boolean }} options.document  `usePlotDocument`'s.
 * @param {ReturnType<typeof import("./useBoardSelection.js").useBoardSelection>} options.selection
 * @param {string} options.path  The file's absolute path, which a copied reference names, as a STEP's do.
 */
export function useBoardHandover({ workspace, document, selection, path }) {
  const { kind, index, words } = document;
  const kicad = kind === "board" || kind === "schematic";
  const { selection: selectors, finding, select, clear } = selection;

  // What is selected, in the prompt grammar: the references a Quick Edit attaches. Null: no index, no Quick Edit.
  const references = useMemo(() => {
    if (!index) return null;
    return selectors.length ? [{ resource: workspace.resource, target: { kind: "cad-selector", selectors: [...selectors] },
      ...(finding?.summary ? { summary: finding.summary } : {}) }] : [];
  }, [index, selectors, finding, workspace.resource]);
  /** The selection (or `named`) as one token naming the file; a chosen check copies with its sentence. */
  const copyText = useCallback((named = selectors) => {
    const token = named.length ? buildBoardRefToken({ path, selectors: named }) : "";
    return named === selectors ? findingCopyText(finding, token) : token;
  }, [selectors, finding, path]);

  // A KiCad document answers select and clearSelection from the start: while it loads, the binding
  // says to wait; once on screen, by its index — or, read without one, in words.
  const live = useMemo(() => {
    if (!kicad) return { declined: words.declined };
    const { select: _select, clearSelection: _clear, ...declined } = words.declined;
    return {
      declined,
      commands: {
        select(request) {
          if (!index) throw new Error(words.declined.select);
          const raw = Array.isArray(request) ? request : Array.isArray(request?.selectors) ? request.selectors : [request?.selector ?? request];
          const list = raw.flatMap((selector) => splitBoardRefSelectors(selector));
          const unknown = list.filter((selector) => !parseBoardRefSelector(selector) || !index.resolve(selector));
          if (unknown.length) {
            throw new Error(index.document === "board"
              ? `Not on this board: ${unknown.join(", ")}. Select board references such as #U3, #U3.9, #net:VIN or #@x10y5.`
              : `Not on this schematic: ${unknown.join(", ")}. Select references such as #U3, #U3.9 or #net:VIN (points are a board's).`);
          }
          select(list);
        },
        clearSelection() {
          if (!index) throw new Error(words.declined.clearSelection);
          clear();
        },
      },
    };
  }, [kicad, words, index, select, clear]);

  // A host asking to select a reference: a document selects it once its index is in; anything else
  // answers rather than dropping it.
  const request = workspace.commands.selectReference ?? null;
  const key = request?.key ?? null;
  const handled = useRef(null);
  const { acknowledgeCommand } = workspace;
  const { loading } = document;
  useEffect(() => {
    if (key === null || handled.current === key) return;
    const named = splitBoardRefSelectors(request?.selector);
    if (index && named.length && named.every((selector) => parseBoardRefSelector(selector))) select(named);
    else if (loading) return;
    handled.current = key;
    acknowledgeCommand?.("selectReference", key);
  }, [key, request, index, select, loading, acknowledgeCommand]);

  return { references, copyText, live };
}
