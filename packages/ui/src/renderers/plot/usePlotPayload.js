/**
 * The plot on screen: one `GET /__cad/plot` for the file, laid out, its sheets decoded.
 *
 * The client never runs the document's tool or parses its file. The server plots it — KiCad
 * draws a board or a schematic with `kicad-cli` — and what arrives is one SVG per sheet, which
 * the browser decodes as images. That is the whole of this renderer's input.
 */
import { useEffect, useMemo, useState } from "react";
import { PLOT_SCHEMA_VERSION, layoutPlot, loadSheetImages } from "@text-to-cad/core/lib/plot2d/index.js";
import { failureAlert } from "../kit/status/loadAlerts.js";

/** A payload from a cadgen that does not agree with this build about the shape. */
class PlotSchemaError extends Error {
  constructor(received) {
    super(
      `The viewer received a plot payload at schemaVersion ${JSON.stringify(received)}, but this `
      + `build of the app reads version ${PLOT_SCHEMA_VERSION}.`
    );
    this.name = "PlotSchemaError";
    this.received = received;
  }
}

/**
 * Load, lay out and decode one plot. A newer revision of the same file is read behind the plot
 * on screen: `loading` is a plot with nothing to show yet, and `updating` the next revision of
 * the one shown, which stays until it arrives — or, if that revision will not read, stays with
 * the error beside it.
 *
 * @param {{ client: import("@text-to-cad/core/client").CadWorkspaceService, file: string, revision?: string }} options
 * @returns {{ plot: { layout: object, images: HTMLImageElement[], board: object|null, schematic: object|null }|null, error: unknown, loading: boolean, updating: boolean }}
 */
export function usePlotPayload({ client, file, revision = "" }) {
  const [state, setState] = useState(() => ({ key: "", file: "", plot: null, error: null, loading: true }));
  const key = useMemo(() => JSON.stringify([file, revision]), [file, revision]);
  useEffect(() => {
    if (!file) {
      setState({ key, file, plot: null, error: new Error("This plot has no file to read."), loading: false });
      return undefined;
    }
    const controller = new AbortController();
    let live = true;
    const shown = (previous) => (previous.file === file ? previous.plot : null);
    setState((previous) => (previous.key === key ? previous : { key, file, plot: shown(previous), error: null, loading: true }));
    client.plotPayload(file, { signal: controller.signal })
      .then(async (payload) => {
        if (payload?.schemaVersion !== PLOT_SCHEMA_VERSION) {
          throw new PlotSchemaError(payload?.schemaVersion);
        }
        const layout = layoutPlot(payload);
        // A board's or a schematic's index rides beside its picture: what its parts, pins and nets are, and where.
        return {
          layout, images: await loadSheetImages(layout, { signal: controller.signal }),
          board: payload.board ?? null, schematic: payload.schematic ?? null
        };
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
 * The alert for a plot that would not load, in the viewer's actionable shape: one heading, an
 * explanation with the server's own sentence — a machine without KiCad is told how to install
 * it, an unreadable board why — and the next step.
 *
 * @param {string} modelKey
 * @param {any} error
 */
export function plotLoadAlert(modelKey, error) {
  if (!error) {
    return null;
  }
  if (error instanceof PlotSchemaError || error?.name === "PlotSchemaError") {
    return {
      severity: "error", kind: "version", summary: "Version mismatch",
      title: "This app and cadgen disagree about plots",
      message: error.message,
      recovery: "Update cadgen and the app together, then reload. They ship from one release for exactly this reason.",
      details: `File: ${modelKey}\nOperation: plotting\n${error.message}`,
      reload: true
    };
  }
  return failureAlert(modelKey, error?.message || error, error?.failure);
}
