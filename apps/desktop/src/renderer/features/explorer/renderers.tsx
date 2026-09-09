import type { RendererRegistration } from "@hardcore/ui/file-viewer";
import { createCadRenderer } from "@hardcore/ui/renderers/cad";
import type { CadCommands } from "@hardcore/ui/renderers/cad";
import { codeRenderer } from "@hardcore/ui/renderers/code";
import { imageRenderer } from "@hardcore/ui/renderers/image";
import { markdownRenderer } from "@hardcore/ui/renderers/markdown";
import { pdfRenderer } from "@hardcore/ui/renderers/pdf";
import { unsupportedRenderer } from "@hardcore/ui/renderers/unsupported";
import { addToDraft } from "@renderer/state/cad-draft";
import { useExplorer } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";
import { CadRuntimeError, createDesktopCadConnection, DesktopCadFailure } from "./adapters/cadRuntime";
import { desktopCadPreferences } from "./adapters/cadPersistence";

/** Application composition: only registered CAD code receives composer/native services. */
export function createDesktopRenderers(projectId: string, root: ExplorerRoot, tabId: string) {
  const connection = createDesktopCadConnection(projectId, root);
  let previousSelection: ReturnType<typeof useExplorer.getState>["cadSelection"];
  let previousCapture: ReturnType<typeof useExplorer.getState>["cadCapture"];
  let snapshot: CadCommands = {};
  const cad = createCadRenderer({
    client: (context) => connection.acquire(context),
    preferences: desktopCadPreferences(),
    onReference: (reference) => addToDraft(projectId, root, { references: [reference] }),
    onPromptContext: (context) => addToDraft(projectId, root, { ...context, deduplicateText: true }),
    onCapture: ({ blob, file, references }) => {
      const stem = (file.split("/").pop() ?? "view").replace(/\.[^.]+$/, "");
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      addToDraft(projectId, root, { references, files: [new File([blob], `${stem}-${stamp}.png`, { type: "image/png" })] });
    },
    commands: {
      subscribe: (listener) => useExplorer.subscribe(listener),
      getSnapshot() {
        const { cadSelection, cadCapture } = useExplorer.getState();
        if (previousSelection !== cadSelection || previousCapture !== cadCapture) {
          previousSelection = cadSelection; previousCapture = cadCapture;
          snapshot = {
            selectReference: cadSelection?.tabId === tabId ? { selector: cadSelection.selector, key: cadSelection.nonce } : null,
            captureRequest: cadCapture?.tabId === tabId ? { key: cadCapture.nonce } : null,
          };
        }
        return snapshot;
      },
    },
  });
  const desktopCad: RendererRegistration = {
    ...cad,
    async prepare(context) {
      try { return await cad.prepare(context); }
      catch (error) {
        context.signal.throwIfAborted();
        if (!(error instanceof CadRuntimeError)) throw error;
        return { Component: (props) => <DesktopCadFailure answer={error.answer} onReady={props.onReady} reload={props.reload} /> };
      }
    },
  };
  return { renderers: [markdownRenderer, codeRenderer, desktopCad, imageRenderer, pdfRenderer, unsupportedRenderer], dispose: () => connection.dispose() };
}
