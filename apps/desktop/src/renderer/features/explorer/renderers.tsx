import { desktopCadLive } from "@renderer/state/live-cad";
import type { PrepareContext, RendererRegistration } from "@hardcore/ui/file-viewer";
import { createCadRenderer } from "@hardcore/ui/renderers/cad";
import { createGlbRenderer } from "@hardcore/ui/renderers/glb";
import { createMeshRenderer } from "@hardcore/ui/renderers/mesh";
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
  // Every viewer renderer shares this tab's backend connection, preferences, host commands and live binding:
  // a tab shows one file, so whichever renderer that file selects is the one that binds them.
  const services = {
    client: (context: PrepareContext) => connection.acquire(context),
    preferences: desktopCadPreferences(),
    commands: createDesktopCadCommands(projectId, root, tabId),
    live: desktopCadLive(tabId, { projectId, root }),
  };
  // A local backend that did not start is a card in the pane, whichever renderer asked for it.
  const withRuntimeFailure = (renderer: RendererRegistration): RendererRegistration => ({
    ...renderer,
    async prepare(context) {
      try { return await renderer.prepare(context); }
      catch (error) {
        context.signal.throwIfAborted();
        if (!(error instanceof CadRuntimeError)) throw error;
        return { Component: (props) => <DesktopCadFailure answer={error.answer} onReady={props.onReady} reload={props.reload} /> };
      }
    },
  });
  const viewers = [createCadRenderer(services), createGlbRenderer(services), createMeshRenderer(services)].map(withRuntimeFailure);
  return { renderers: [markdownRenderer, codeRenderer, ...viewers, imageRenderer, pdfRenderer, unsupportedRenderer], dispose: () => ownedConnection?.dispose() };
}
