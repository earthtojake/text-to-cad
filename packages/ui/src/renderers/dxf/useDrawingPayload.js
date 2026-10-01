/**
 * The drawing on screen: one `GET /__cad/drawing` for the file, batched into
 * paths once.
 *
 * The client never parses DXF. ezdxf does the reading on the server — text
 * outlined, dimensions exploded, hatches filled, blocks placed — and what
 * arrives is a flat list of five primitive shapes in drawing coordinates. That
 * is the whole of this renderer's input.
 */
import { useEffect, useMemo, useState } from "react";
import { DRAWING_SCHEMA_VERSION, prepareDrawing } from "@text-to-cad/core/lib/drawing2d/index.js";
import { failureAlert } from "../kit/status/loadAlerts.js";

/** A payload from a cadgen that does not agree with this build about the shape. */
class DrawingSchemaError extends Error {
  constructor(received) {
    super(
      `The viewer received a drawing payload at schemaVersion ${JSON.stringify(received)}, but this `
      + `build of the app reads version ${DRAWING_SCHEMA_VERSION}.`
    );
    this.name = "DrawingSchemaError";
    this.received = received;
  }
}

/**
 * Load and prepare one drawing. A newer revision of the same file is read behind
 * the drawing on screen: `loading` is a drawing with nothing to show yet, and
 * `updating` the next revision of the one shown, which stays until it arrives —
 * or, if that revision will not read, stays with the error beside it.
 *
 * @param {{ client: import("@text-to-cad/core/client").CadWorkspaceService, file: string, revision?: string }} options
 * @returns {{ drawing: object|null, error: unknown, loading: boolean, updating: boolean }}
 */
export function useDrawingPayload({ client, file, revision = "" }) {
  const [state, setState] = useState(() => ({ key: "", file: "", drawing: null, error: null, loading: true }));
  const key = useMemo(() => JSON.stringify([file, revision]), [file, revision]);
  useEffect(() => {
    if (!file) {
      setState({ key, file, drawing: null, error: new Error("This drawing has no file to read."), loading: false });
      return undefined;
    }
    const controller = new AbortController();
    let live = true;
    const shown = (previous) => (previous.file === file ? previous.drawing : null);
    setState((previous) => (previous.key === key ? previous : { key, file, drawing: shown(previous), error: null, loading: true }));
    client.drawing(file, { signal: controller.signal })
      .then((payload) => {
        if (payload?.schemaVersion !== DRAWING_SCHEMA_VERSION) {
          throw new DrawingSchemaError(payload?.schemaVersion);
        }
        return prepareDrawing(payload);
      })
      .then((drawing) => { if (live) setState({ key, file, drawing, error: null, loading: false }); })
      .catch((error) => {
        if (!live || controller.signal.aborted) return;
        setState((previous) => ({ key, file, drawing: shown(previous), error, loading: false }));
      });
    return () => { live = false; controller.abort(); };
  }, [client, file, key]);
  const current = state.key === key;
  const drawing = current || state.file === file ? state.drawing : null;
  const pending = !current || state.loading;
  return { drawing, error: current ? state.error : null, loading: pending && !drawing, updating: pending && Boolean(drawing) };
}

/**
 * The alert for a drawing that would not load, in the viewer's actionable
 * shape: one heading, an explanation with the server's own sentence, and the
 * next step.
 *
 * @param {string} modelKey
 * @param {any} error
 */
export function drawingLoadAlert(modelKey, error) {
  if (!error) {
    return null;
  }
  if (error instanceof DrawingSchemaError || error?.name === "DrawingSchemaError") {
    return {
      severity: "error", kind: "version", summary: "Version mismatch",
      title: "This app and cadgen disagree about drawings",
      message: error.message,
      recovery: "Update cadgen and the app together, then reload. They ship from one release for exactly this reason.",
      details: `File: ${modelKey}\nOperation: drawing\n${error.message}`,
      reload: true
    };
  }
  return failureAlert(modelKey, error?.message || error, error?.failure);
}
