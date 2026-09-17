import type { RendererRegistration } from "@hardcore/ui/file-viewer";
import { createCadRenderer } from "@hardcore/ui/renderers/cad";
import { codeRenderer } from "@hardcore/ui/renderers/code";
import { imageRenderer } from "@hardcore/ui/renderers/image";
import { markdownRenderer } from "@hardcore/ui/renderers/markdown";
import { pdfRenderer } from "@hardcore/ui/renderers/pdf";
import { unsupportedRenderer } from "@hardcore/ui/renderers/unsupported";
import type { ExplorerRoot } from "@shared/types";
import { CadRuntimeError, createDesktopCadConnection, DesktopCadFailure } from "./adapters/cadRuntime";
import type { DesktopCadConnection } from "./adapters/cadRuntime";
import { desktopCadPreferences } from "./adapters/cadPersistence";
import { createDesktopCadCommands } from "./host/cadCommands";

/** Application composition: only registered CAD code receives composer/native services. */
export function createDesktopRenderers(projectId: string, root: ExplorerRoot, tabId: string, borrowedConnection?: DesktopCadConnection) {
  const ownedConnection = borrowedConnection ? null : createDesktopCadConnection(projectId, root);
  const connection = borrowedConnection ?? ownedConnection!;
  const cad = createCadRenderer({
    client: (context) => connection.acquire(context),
    preferences: desktopCadPreferences(),
    commands: createDesktopCadCommands(projectId, root, tabId),
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
  return { renderers: [markdownRenderer, codeRenderer, desktopCad, imageRenderer, pdfRenderer, unsupportedRenderer], dispose: () => ownedConnection?.dispose() };
}
