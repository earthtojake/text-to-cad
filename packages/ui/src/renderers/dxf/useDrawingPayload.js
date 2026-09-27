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
import { DRAWING_SCHEMA_VERSION, prepareDrawing } from "@hardcore/core/lib/drawing2d/index.js";
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
 * Load and prepare one drawing.
 *
 * @param {{ client: import("@hardcore/core/client").CadWorkspaceService, file: string, revision?: string }} options
 * @returns {{ drawing: object|null, error: unknown, loading: boolean }}
 */
export function useDrawingPayload({ client, file, revision = "" }) {
  const [state, setState] = useState(() => ({ key: "", drawing: null, error: null, loading: true }));
  const key = useMemo(() => JSON.stringify([file, revision]), [file, revision]);
  useEffect(() => {
    if (!file) {
      setState({ key, drawing: null, error: new Error("This drawing has no file to read."), loading: false });
      return undefined;
    }
    const controller = new AbortController();
    let live = true;
    setState((previous) => (previous.key === key ? previous : { key, drawing: null, error: null, loading: true }));
    client.drawing(file, { signal: controller.signal })
      .then((payload) => {
        if (payload?.schemaVersion !== DRAWING_SCHEMA_VERSION) {
          throw new DrawingSchemaError(payload?.schemaVersion);
        }
        return prepareDrawing(payload);
      })
      .then((drawing) => { if (live) setState({ key, drawing, error: null, loading: false }); })
      .catch((error) => {
        if (!live || controller.signal.aborted) return;
        setState({ key, drawing: null, error, loading: false });
      });
    return () => { live = false; controller.abort(); };
  }, [client, file, key]);
  return { drawing: state.key === key ? state.drawing : null, error: state.key === key ? state.error : null,
    loading: state.key !== key || state.loading };
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
