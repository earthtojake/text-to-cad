import type { SshClientProxy } from '@core/primitives/ssh/api/node/ssh-client-proxy';

export type WorkspaceServerSshPort = {
  ensureProxy(connectionId: string): Promise<SshClientProxy>;
};
