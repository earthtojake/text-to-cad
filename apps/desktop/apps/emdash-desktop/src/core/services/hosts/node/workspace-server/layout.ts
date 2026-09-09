import path from 'node:path';

export type WorkspaceServerLayout = {
  home: string;
  root: string;
  versionsDirectory: string;
  currentLink: string;
  stagingDirectory: string;
  installLock: string;
  runDirectory: string;
  socketPath: string;
  versionDirectory(version: string): string;
  versionLauncher(version: string): string;
  currentLauncher: string;
};

export function workspaceServerLayout(home: string): WorkspaceServerLayout {
  validateRemoteHome(home);
  const root = path.posix.join(home, '.emdash/workspace-server');
  const versionsDirectory = path.posix.join(root, 'versions');
  const currentLink = path.posix.join(root, 'current');

  return {
    home,
    root,
    versionsDirectory,
    currentLink,
    stagingDirectory: path.posix.join(root, 'staging'),
    installLock: path.posix.join(root, 'install.lock'),
    runDirectory: path.posix.join(root, 'run'),
    socketPath: path.posix.join(root, 'run/workspace.sock'),
    versionDirectory(version) {
      return path.posix.join(versionsDirectory, validateWorkspaceServerVersion(version));
    },
    versionLauncher(version) {
      return path.posix.join(
        versionsDirectory,
        validateWorkspaceServerVersion(version),
        'bin/emdash-workspace-server'
      );
    },
    currentLauncher: path.posix.join(currentLink, 'bin/emdash-workspace-server'),
  };
}

export function validateWorkspaceServerVersion(version: string): string {
  if (
    !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/.test(
      version
    )
  ) {
    throw new Error(`Invalid workspace-server version '${version}'`);
  }
  return version;
}

function validateRemoteHome(home: string): void {
  if (
    !path.posix.isAbsolute(home) ||
    home.includes('\0') ||
    home.includes('\n') ||
    home.includes('\r') ||
    path.posix.normalize(home) !== home ||
    (home.length > 1 && home.endsWith('/'))
  ) {
    throw new Error(`Invalid remote home directory '${home}'`);
  }
}
