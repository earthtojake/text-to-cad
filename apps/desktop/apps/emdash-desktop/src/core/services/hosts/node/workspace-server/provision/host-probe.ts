import type { WorkspaceServerSshPort } from '../ports';

export type RemoteHostInfo = {
  home: string;
};

export class RemoteHostProbe {
  private readonly cache = new Map<string, Promise<RemoteHostInfo>>();

  constructor(private readonly ssh: WorkspaceServerSshPort) {}

  probe(connectionId: string, signal?: AbortSignal): Promise<RemoteHostInfo> {
    const cached = this.cache.get(connectionId);
    if (cached) return cached;

    const pending = this.probeUncached(connectionId, signal).catch((error: unknown) => {
      if (this.cache.get(connectionId) === pending) this.cache.delete(connectionId);
      throw error;
    });
    this.cache.set(connectionId, pending);
    return pending;
  }

  drop(connectionId: string): void {
    this.cache.delete(connectionId);
  }

  private async probeUncached(connectionId: string, signal?: AbortSignal): Promise<RemoteHostInfo> {
    const proxy = await this.ssh.ensureProxy(connectionId);
    const result = await proxy.execScript(`printf '%s\\n' "$HOME"`, {
      signal,
      timeoutMs: 10_000,
      maxStdoutBytes: 4_096,
      maxStderrBytes: 4_096,
    });
    if (result.exitCode !== 0) {
      throw new Error(`Remote host probe failed: ${result.stderr.trim() || result.exitCode}`);
    }
    const home = result.stdout.trim();
    if (!home) {
      throw new Error('Remote host probe returned an incomplete response');
    }

    return { home };
  }
}
