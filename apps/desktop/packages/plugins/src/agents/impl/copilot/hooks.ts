import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import type { HookRegistration } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  EMDASH_MARKER,
  buildFlatEntry,
  configRoots,
  envConfigRoot,
  filterUserHooks,
  hookMapFromConfig,
  makeNotificationHookCommand,
  makeStdinHookCommand,
  readJsonConfig,
  writeJsonConfig,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const COPILOT_HOOKS_PATH = 'hooks/emdash.json';

export function buildCopilotHookConfig() {
  const stopCmd = makeStdinHookCommand('stop');
  const sessionCmd = makeStdinHookCommand('session');
  const permCmd = makeNotificationHookCommand('permission_prompt');

  return {
    resolveConfigRoots: configRoots(envConfigRoot('COPILOT_HOME', '.copilot')),
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readJsonConfig(fs, COPILOT_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, COPILOT_HOOKS_PATH);
      const installed = [
        ['agentStop', stopCmd],
        ['sessionStart', sessionCmd],
        ['permissionRequest', permCmd],
      ].every(([key, command]) => {
        const entries = Array.isArray(hooks[key]) ? hooks[key] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildFlatEntry(command))
        );
      });
      return installed ? [{ event: 'emdash', command: EMDASH_MARKER }] : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readJsonConfig(fs, COPILOT_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, COPILOT_HOOKS_PATH);

      const stopExisting = Array.isArray(hooks.agentStop) ? hooks.agentStop : [];
      hooks.agentStop = [...filterUserHooks(stopExisting), buildFlatEntry(stopCmd)];
      const sessionExisting = Array.isArray(hooks.sessionStart) ? hooks.sessionStart : [];
      hooks.sessionStart = [...filterUserHooks(sessionExisting), buildFlatEntry(sessionCmd)];
      const permExisting = Array.isArray(hooks.permissionRequest) ? hooks.permissionRequest : [];
      hooks.permissionRequest = [...filterUserHooks(permExisting), buildFlatEntry(permCmd)];
      if (Array.isArray(hooks.notification)) {
        hooks.notification = filterUserHooks(hooks.notification);
      }

      await writeJsonConfig(fs, COPILOT_HOOKS_PATH, { ...config, version: 1, hooks });
      return [COPILOT_HOOKS_PATH];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readJsonConfig(fs, COPILOT_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, COPILOT_HOOKS_PATH);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeJsonConfig(fs, COPILOT_HOOKS_PATH, { ...config, hooks });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readJsonConfig(fs, COPILOT_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, COPILOT_HOOKS_PATH);
      return [
        ['agentStop', stopCmd],
        ['sessionStart', sessionCmd],
        ['permissionRequest', permCmd],
      ].every(([key, command]) => {
        const entries = Array.isArray(hooks[key]) ? hooks[key] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildFlatEntry(command))
        );
      });
    },
  };
}
