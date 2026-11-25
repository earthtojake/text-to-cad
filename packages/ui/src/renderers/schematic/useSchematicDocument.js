import { useI18n } from "@cad/ui/i18n";
import { useEffect, useMemo, useRef, useState } from "react";
import { PLOT_SCHEMA_VERSION, layoutPlot } from "@cad/core/lib/plot2d/index.js";
import { createSchematicIndex, createSchematicPage } from "@cad/core/lib/schematic2d/schematicIndex.js";
import { canonicalSheetPath } from "@cad/core/lib/schematicRefs.js";
import { failureAlert } from "../kit/status/loadAlerts.js";

/**
 * The schematic on screen: the sheet shown, read from the server a sheet at a time
 * (`GET /api/v1/documents/kicad_sch/<id>/plot?sheet=<path>`, `plotPayload`'s `sheet`), the hierarchy's
 * index with the first sheet read of each revision (`index`: every sheet, part, pin and net) and each
 * sheet after it without (`index: false`). A sheet read is kept for its revision, so going back to it is
 * instant; a new revision of the file reads the sheet on screen again behind the one shown, which stays
 * (`updating`) until it arrives — or, if it will not read, stays with the error beside it. The client
 * never parses KiCad's files.
 *
 * @param {{ workspace: ReturnType<typeof import("../workspace/useWorkspaceDocument.js").useWorkspaceDocument>, path: string, sheet: string }} options
 */
export function useSchematicDocument({ workspace, path, sheet }) {
  const { t } = useI18n();
  const file = workspace.entry?.file || path;
  const revision = String(workspace.resource.revision || "");
  const client = workspace.client;
  const wanted = canonicalSheetPath(sheet || "/");
  // What has been read: the revision it is of, its index, and its sheets, each laid out.
  const [read, setRead] = useState(() => ({ key: "", file: "", index: null, pages: new Map(), error: null, failed: "" }));
  const readRef = useRef(read);
  readRef.current = read;
  const key = JSON.stringify([file, revision]);
  // The sheet to show: the one asked for once the index has it, else the root.
  const target = read.index && !read.index.sheets.has(wanted) ? read.index.root : wanted;
  const current = read.key === key;
  useEffect(() => {
    if (!file) {
      setRead({ key, file, index: null, pages: new Map(), error: new Error("This schematic has no file to read."), failed: "" });
      return undefined;
    }
    const known = readRef.current;
    const fresh = known.key !== key;
    if (!fresh && (known.pages.has(target) || known.failed === target)) return undefined;
    const controller = new AbortController();
    let live = true;
    const withIndex = fresh || !known.index;
    client.plotPayload(file, { signal: controller.signal, sheet: target, ...(withIndex ? {} : { index: false }) })
      .then((payload) => {
        if (payload?.schemaVersion !== PLOT_SCHEMA_VERSION) {
          const error = new Error(`The viewer received a schematic payload at schemaVersion ${JSON.stringify(payload?.schemaVersion)}, but this `
            + `build of the app reads version ${PLOT_SCHEMA_VERSION}.`);
          error.name = "SchematicSchemaError";
          throw error;
        }
        const layout = layoutPlot(payload);
        if (!live) return;
        setRead((previous) => {
          const same = previous.key === key;
          const index = withIndex ? (payload.schematic ? createSchematicIndex(payload.schematic) : null) : previous.index;
          const pages = new Map(same ? previous.pages : []);
          pages.set(target, { layout, plot: { layout }, page: index ? createSchematicPage(index, layout.sheets[0]) : null });
          return { key, file, index, pages, error: null, failed: "" };
        });
      })
      .catch((error) => {
        if (!live || controller.signal.aborted) return;
        setRead((previous) => ({ ...previous, error, failed: target }));
      });
    return () => { live = false; controller.abort(); };
  }, [client, file, key, target]);

  // On screen: this revision's sheet, else the one shown before it while the new one is read.
  const fromFile = read.file === file;
  const shownPage = fromFile ? read.pages.get(target) || null : null;
  // Each sheet read is one object for as long as it is kept: the view draws a new plot afresh.
  const shownBefore = useRef(null);
  const page = shownPage ? (shownBefore.current?.entry === shownPage ? shownBefore.current : { sheet: target, entry: shownPage, ...shownPage })
    : fromFile ? shownBefore.current : null;
  if (shownPage) shownBefore.current = page;
  const plot = page ? page.plot : null;
  const index = fromFile ? read.index : null;
  const pending = !current || (!read.pages.has(target) && read.failed !== target);
  const shown = Boolean(plot);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: t("schematic.text.couldn_t_open_the_schematic"),
        message: t("alert.catalogFailed"), recovery: t("alert.catalogRecovery"), details: String(workspace.catalogError), reload: true
      };
    }
    const error = read.error;
    if (!error) return null;
    if (error.name === "SchematicSchemaError") {
      return { severity: "error", kind: "version", summary: t("alert.schema.summary"), title: t("schematic.text.this_app_and_the_server_disagree_about_schematics"),
        message: error.message, recovery: t("alert.schema.recovery"), details: `File: ${workspace.modelKey || file}\nOperation: plotting\n${error.message}`, reload: true };
    }
    const failed = failureAlert(workspace.modelKey || file, error?.message || error, error?.failure);
    return failed && shown ? { ...failed, blocking: false, message: t("schematic.text.message_the_existing_schematic_remains_visible", { message: failed.message }) } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, read.error, shown, t]);

  return {
    file, plot, index, page: page?.page ?? null, sheet: page?.sheet ?? null, target, shown, alert,
    loading: pending && !shown, updating: pending && shown
  };
}
