/**
 * The CAD plugin's page half: the shared CAD Viewer renderers (`@hardcore/ui/renderers/*`) wired to
 * this app's CAD backend, and its agent commands answered from the live viewer.
 */
import { isCadFile } from "@hardcore/core/lib/fileFormats.js";
import type { PrepareContext, RendererRegistration } from "@hardcore/ui/file-viewer";
import { createDxfRenderer } from "@hardcore/ui/renderers/dxf";
import { createGlbRenderer } from "@hardcore/ui/renderers/glb";
import { createMeshRenderer } from "@hardcore/ui/renderers/mesh";
import { createRobotRenderer } from "@hardcore/ui/renderers/robot";
import { createStepRenderer } from "@hardcore/ui/renderers/step";
import { CadRuntimeError, createDesktopCadConnection, DesktopCadFailure } from "@renderer/features/explorer/adapters/cadRuntime";
import { desktopCadPreferences } from "@renderer/features/explorer/adapters/cadPersistence";
import { createDesktopCadCommands } from "@renderer/features/explorer/host/cadCommands";
import { desktopCadLive, performCadViewerCommand } from "@renderer/state/live-cad";

import type { RendererPlugin } from "../renderer";
import manifest from "./manifest.mjs";

const cad: RendererPlugin = {
  manifest,
  viewers({ projectId, root, tabId, cadConnection }) {
    // A tab borrows the project's backend for its root when the host shares one, else starts its own.
    const owned = cadConnection ? null : createDesktopCadConnection(projectId, root);
    const connection = cadConnection ?? owned!;
    // Every CAD renderer shares this tab's backend, preferences, host commands and live binding: a
    // tab shows one file, so whichever renderer that file selects is the one that binds them.
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
    const renderers = [createStepRenderer(services), createDxfRenderer(services), createGlbRenderer(services), createMeshRenderer(services), createRobotRenderer(services)];
    return { renderers: renderers.map(withRuntimeFailure), dispose: () => owned?.dispose() };
  },
  async perform(kind, params, scope) {
    if (!isCadFile(scope.path)) throw new Error("this tab does not contain a CAD model");
    return performCadViewerCommand(kind as Parameters<typeof performCadViewerCommand>[0], params, scope);
  },
};
export default cad;
