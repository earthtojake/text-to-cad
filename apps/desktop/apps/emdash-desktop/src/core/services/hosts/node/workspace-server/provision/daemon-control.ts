import type { WorkspaceServerLayout } from '../layout';
import type { WorkspaceServerSshPort } from '../ports';

export class WorkspaceServerDaemonError extends Error {
  readonly name = 'WorkspaceServerDaemonError';
}

export class RemoteWorkspaceServerDaemon {
  constructor(private readonly ssh: WorkspaceServerSshPort) {}

  start(connectionId: string, layout: WorkspaceServerLayout, signal?: AbortSignal): Promise<void> {
    return this.run(connectionId, layout, 'start', signal);
  }

  stop(connectionId: string, layout: WorkspaceServerLayout, signal?: AbortSignal): Promise<void> {
    return this.run(connectionId, layout, 'stop', signal);
  }

  status(connectionId: string, layout: WorkspaceServerLayout, signal?: AbortSignal): Promise<void> {
    return this.run(connectionId, layout, 'status', signal);
  }

  async restart(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal?: AbortSignal
  ): Promise<void> {
    await this.stop(connectionId, layout, signal).catch(() => {});
    await this.start(connectionId, layout, signal);
  }

  private async run(
    connectionId: string,
    layout: WorkspaceServerLayout,
    action: 'start' | 'stop' | 'status',
    signal?: AbortSignal
  ): Promise<void> {
    const proxy = await this.ssh.ensureProxy(connectionId);
    const result = await proxy.exec(
      {
        command: layout.currentLauncher,
        args: [action, '--socket', layout.socketPath],
      },
      {
        signal,
        timeoutMs: 30_000,
        maxStdoutBytes: 64 * 1_024,
        maxStderrBytes: 64 * 1_024,
      }
    );
    if (result.exitCode !== 0) {
      throw new WorkspaceServerDaemonError(
        `Workspace-server ${action} failed: ${result.stderr.trim() || `exit ${result.exitCode}`}`
      );
    }
  }
}
