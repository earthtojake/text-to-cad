/**
 * `plugins.*` handlers — stubs.
 *
 * P5 composes the bundled plugin (`resources/plugin/`) and installs it into
 * each agent through the `pluginInstall` argv in the registry. Until it does,
 * the honest answer is that nothing is installed, and install is a no-op that
 * says so: an Install button that reported success without installing anything
 * would be a worse lie than a button that does not work yet.
 *
 * The shape is not a stub, though. Every field the drawer and the CAD Runtime
 * page render is answered here, so P5 replaces the bodies and touches no UI.
 */
import { app } from "electron";

import type { IpcHandlers } from "../../shared/ipc";
import type { PluginStatus, pluginsContract } from "../../shared/ipc/plugins";
import { AGENT_PROVIDERS, agentProvider } from "../agents/registry";
import { IpcError, type IpcContext } from "./register";

/** The version P5 will install: the app's own (plan §8). */
function appVersion(): string {
  return app.isPackaged ? app.getVersion() : __APP_VERSION__;
}

function statusFor(agentId: string): PluginStatus {
  const provider = agentProvider(agentId);
  if (!provider) {
    throw new IpcError(`unknown agent: ${agentId}`);
  }
  return {
    agentId,
    // An agent with neither a plugin system nor a skills directory has nowhere
    // to put the plugin, and that is a different answer from "not yet".
    state: provider.pluginInstall || provider.skillsDir ? "not-installed" : "unsupported",
    installedVersion: null,
    availableVersion: appVersion(),
    mcpServers: 0,
  };
}

export const pluginsHandlers = {
  plugins: {
    status: ({ agentId }) => statusFor(agentId),

    statusAll: () => AGENT_PROVIDERS.map((provider) => statusFor(provider.id)),

    // P5: compose, register the marketplace, install, then broadcast
    // `plugins.status`. Answering with the unchanged state keeps the button
    // honest — the drawer shows "not installed" again rather than a version
    // that does not exist.
    install: ({ agentId }) => ({
      ...statusFor(agentId),
      message: "Installing the Hardcore plugin arrives with the CAD runtime (P5).",
    }),
  },
} satisfies IpcHandlers<typeof pluginsContract, IpcContext>;
