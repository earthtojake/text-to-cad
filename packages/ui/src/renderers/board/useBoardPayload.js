import { english } from "@text-to-cad/ui/i18n";
/**
 * The board on screen: one `GET /__cad/plot` for the file, laid out.
 *
 * The client never parses the board's file. The server reads it and answers geometry per layer,
 * which `layoutPlot` validates and lays out; the board's index rides beside it. That is the whole
 * of this renderer's input.
 */
import { useEffect, useMemo, useState } from "react";
import { PLOT_SCHEMA_VERSION, layoutPlot } from "@text-to-cad/core/lib/plot2d/index.js";
import { failureAlert } from "../kit/status/loadAlerts.js";

/** A payload from a cadgen that does not agree with this build about the shape. */
class BoardSchemaError extends Error {
  constructor(received) {
    super(
      `The viewer received a board payload at schemaVersion ${JSON.stringify(received)}, but this `
      + `build of the app reads version ${PLOT_SCHEMA_VERSION}.`
    );
    this.name = "BoardSchemaError";
    this.received = received;
  }
}

/**
 * Load and lay out one board. A newer revision of the same file is read behind the board on
 * screen: `loading` is a board with nothing to show yet, and `updating` the next revision of the
 * one shown, which stays until it arrives — or, if that revision will not read, stays with the
 * error beside it.
 *
 * @param {{ client: import("@text-to-cad/core/client").CadWorkspaceService, file: string, revision?: string }} options
 * @returns {{ plot: { layout: object, board: object|null }|null, error: unknown, loading: boolean, updating: boolean }}
 */
export function useBoardPayload({ client, file, revision = "" }) {
  const [state, setState] = useState(() => ({ key: "", file: "", plot: null, error: null, loading: true }));
  const key = useMemo(() => JSON.stringify([file, revision]), [file, revision]);
  useEffect(() => {
    if (!file) {
      setState({ key, file, plot: null, error: new Error("This board has no file to read."), loading: false });
      return undefined;
    }
    const controller = new AbortController();
    let live = true;
    const shown = (previous) => (previous.file === file ? previous.plot : null);
    setState((previous) => (previous.key === key ? previous : { key, file, plot: shown(previous), error: null, loading: true }));
    client.plotPayload(file, { signal: controller.signal })
      .then((payload) => {
        if (payload?.schemaVersion !== PLOT_SCHEMA_VERSION) {
          throw new BoardSchemaError(payload?.schemaVersion);
        }
        // The board's index rides beside its picture: what its parts, pads and nets are, and where.
        return { layout: layoutPlot(payload), board: payload.board ?? null };
      })
      .then((plot) => { if (live) setState({ key, file, plot, error: null, loading: false }); })
      .catch((error) => {
        if (!live || controller.signal.aborted) return;
        setState((previous) => ({ key, file, plot: shown(previous), error, loading: false }));
      });
    return () => { live = false; controller.abort(); };
  }, [client, file, key]);
  const current = state.key === key;
  const plot = current || state.file === file ? state.plot : null;
  const pending = !current || state.loading;
  return { plot, error: current ? state.error : null, loading: pending && !plot, updating: pending && Boolean(plot) };
}

/**
 * The alert for a board that would not load, in the viewer's actionable shape: one heading, an
 * explanation with the server's own sentence — an unreadable board says why — and the next step.
 *
 * @param {string} modelKey
 * @param {any} error
 */
export function boardLoadAlert(modelKey, error, t = english) {
  if (!error) {
    return null;
  }
  if (error instanceof BoardSchemaError || error?.name === "BoardSchemaError") {
    return {
      severity: "error", kind: "version", summary: t("alert.schema.summary"),
      title: t("board.text.this_app_and_cadgen_disagree_about_boards"),
      message: error.message,
      recovery: t("alert.schema.recovery"),
      details: `File: ${modelKey}\nOperation: plotting\n${error.message}`,
      reload: true
    };
  }
  return failureAlert(modelKey, error?.message || error, error?.failure);
}
