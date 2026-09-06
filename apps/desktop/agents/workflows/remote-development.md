# Remote Development

## Current Model

Remote functionality is owned by the workspace server runtime. The Electron app
keeps SSH connection management for transport, credentials, host config parsing,
and external "open in SSH" integrations, but runtime behavior should go through
the workspace-server wire contract instead of desktop-side SSH exec, SFTP, PTY,
or shell-profile code.

## Main Files

- `apps/workspace-server/src/` — daemon entry point, socket serving, runtime wiring
- `packages/core/src/workspace-server/` — shared wire contract, schemas, protocol
  versioning, and workspace-server-specific APIs
- `packages/core/src/workspace-server/releases.ts` — channel-pointer schema, strict
  release versions, and protocol-major pointer paths
- `src/core/services/ssh/` — desktop SSH connection management, credentials, config
  parsing, and transport setup
- `src/core/services/hosts/` — managed remote install/ensure flow and the
  reconnecting Wire client over SSH streamlocal forwarding
- `src/main/core/wire-workers/` — desktop-local wire runtime workers for local
  projects while remote runtimes are served by the workspace server
- `src/main/host/remoteOpenIn.ts` — external SSH URL/command helper that
  intentionally bypasses workspace-server runtimes

## Authentication And Storage

- SSH credentials are managed through the SSH services and OS-backed secret storage
- host key handling is implemented under `src/main/core/ssh/`
- runtime dependency state for remote hosts belongs to the workspace-server
  `hostDependencies` component, not an Electron-side SSH execution context
- the desktop owns the managed install under `~/.emdash/workspace-server`; remote
  runtime calls begin only after the workspace-server provisioner reports ready
- managed installs read the desktop channel's pointer for its protocol major, then
  run the immutable versioned `install.sh` with the pointer's artifact version pinned

## Rules

- treat all shell construction as security-sensitive
- use shared SSH and shell-escaping helpers instead of ad hoc quoting
- do not add new desktop-side SSH exec, SFTP, PTY, or shell-profile paths for
  runtime behavior; add or consume workspace-server wire APIs instead
- desktop-side SSH exec is limited to the workspace-server control plane: probing
  the host, checksum-verified installation, and daemon lifecycle commands
- port-forward preview control belongs in `workspaceWireContract.portForwards`;
  data streams should be transport-native once the workspace-server client layer
  exists
- confirm whether a feature is local-only before assuming parity on remote projects
