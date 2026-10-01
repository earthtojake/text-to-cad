import { desktopCadLive } from "@renderer/state/live-cad";
import type { PrepareContext, RendererRegistration } from "@text-to-cad/ui/file-viewer";
import { createStepRenderer } from "@text-to-cad/ui/renderers/step";
import { createDxfRenderer } from "@text-to-cad/ui/renderers/dxf";
import { createGlbRenderer } from "@text-to-cad/ui/renderers/glb";
import { createMeshRenderer } from "@text-to-cad/ui/renderers/mesh";
import { createRobotRenderer } from "@text-to-cad/ui/renderers/robot";
import type { ExplorerRoot } from "@shared/types";
import { CadRuntimeError, createDesktopCadConnection, DesktopCadFailure } from "../adapters/cadRuntime";
import type { DesktopCadConnection } from "../adapters/cadRuntime";
import { desktopTabStore } from "../adapters/tabStore";
import { createDesktopCadCommands } from "../host/cadCommands";
import { codeRenderer } from "./code";
import { imageRenderer } from "./image";
import { markdownRenderer } from "./markdown";
import { pdfRenderer } from "./pdf";
import { unsupportedRenderer } from "./unsupported";

/**
 * Application composition: the shared viewer renderers (`@text-to-cad/ui/renderers/*`) and this
 * app's own — Markdown, code, image, PDF and the unsupported fallback, which only the desktop
 * registers and which live beside this file. Only registered CAD code receives composer/native
 * services.
 */
export function createDesktopRenderers(projectId: string, root: ExplorerRoot, tabId: string, borrowedConnection?: DesktopCadConnection) {
  const ownedConnection = borrowedConnection ? null : createDesktopCadConnection(projectId, root);
  const connection = borrowedConnection ?? ownedConnection!;
  // Every viewer renderer shares this tab's backend connection, its tab store's settings, host commands and
  // live binding: a tab shows one file, so whichever renderer that file selects is the one that binds them.
  const services = {
    client: (context: PrepareContext) => connection.acquire(context),
    preferences: desktopTabStore(tabId).settings,
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
  const viewers = [createStepRenderer(services), createDxfRenderer(services), createGlbRenderer(services), createMeshRenderer(services), createRobotRenderer(services)].map(withRuntimeFailure);
  return { renderers: [markdownRenderer, codeRenderer, ...viewers, imageRenderer, pdfRenderer, unsupportedRenderer], dispose: () => ownedConnection?.dispose() };
}
