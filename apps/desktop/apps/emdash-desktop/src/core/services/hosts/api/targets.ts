export type LocalWorkspaceServerTarget = {
  kind: 'local-socket';
  socketPath: string;
};

export type SshWorkspaceServerTarget = {
  kind: 'ssh';
  sshConnectionId: string;
  socketPath: string;
};

export type WorkspaceServerTarget = LocalWorkspaceServerTarget | SshWorkspaceServerTarget;
