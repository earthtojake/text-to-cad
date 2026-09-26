/**
 * Handlers for `plugins.*` (src/shared/ipc/plugins.ts).
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { pluginsContract } from "../../shared/ipc/plugins";
import { plugins } from "../../plugins/index.mjs";
import { allPluginIntegrations, pluginEnabled } from "../../plugins/main.mjs";
import type { IpcContext } from "./register";

export const pluginsHandlers = {
  plugins: {
    list: () => plugins.map((plugin) => ({
      id: plugin.id,
      name: plugin.name,
      description: plugin.description,
      enabled: pluginEnabled(plugin.id),
      extensions: plugin.fileTypes.flatMap((type) => [...type.extensions]),
      skills: [...plugin.skills.map((skill) => skill.split("/").at(-1) ?? skill), ...plugin.repoSkills],
      tools: allPluginIntegrations.find((integration) => integration.id === plugin.id)?.tools.map((tool) => tool.name) ?? [],
    })),
  },
} satisfies IpcHandlers<typeof pluginsContract, IpcContext>;
