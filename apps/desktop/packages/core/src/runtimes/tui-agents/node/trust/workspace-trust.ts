import path from 'node:path';
import type { Logger } from '@emdash/shared/logger';
import type { AgentPluginHost, ITrustBehavior } from '#services/agent-plugins/api/plugins';
import { createLocalPluginFs } from '#services/agent-plugins/api/plugins/helpers';

export type TuiWorkspaceTrustOptions = {
  agentHost: AgentPluginHost;
  logger: Logger;
};

export class TuiWorkspaceTrust {
  private writeLock: Promise<void> = Promise.resolve();

  constructor(private readonly options: TuiWorkspaceTrustOptions) {}

  async ensureTrusted(params: { providerId: string; workspacePath: string }): Promise<void> {
    const behavior = this.options.agentHost.get(params.providerId)?.behavior.trust;
    if (!behavior) return;

    if (!path.isAbsolute(params.workspacePath)) {
      this.options.logger.warn('TuiWorkspaceTrust: refusing to trust non-absolute workspace path', {
        providerId: params.providerId,
        workspacePath: params.workspacePath,
      });
      return;
    }

    const workspacePath = path.normalize(params.workspacePath);
    const run = () => this.applyTrust(behavior, params.providerId, workspacePath);
    const next = this.writeLock.then(run, run);
    this.writeLock = next;
    await next;
  }

  private async applyTrust(
    behavior: ITrustBehavior,
    providerId: string,
    workspacePath: string
  ): Promise<void> {
    try {
      await behavior.trustWorkspace(createLocalPluginFs(this.options.agentHost.homeDir), {
        workspacePath,
      });
    } catch (error) {
      this.options.logger.warn('TuiWorkspaceTrust: failed to trust workspace', {
        providerId,
        workspacePath,
        error: String(error),
      });
    }
  }
}
