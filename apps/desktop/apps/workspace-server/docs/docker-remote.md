# Docker Remote Machine

The package-owned `workspace-remote` Compose service is a deliberately bare SSH host for exercising
the complete desktop-to-workspace-server connection path. It includes SSH, Git, tmux, and basic
process tools, but no Node.js, npm, ripgrep, build toolchain, or coding-agent CLI. Content search
therefore verifies that the installed workspace-server artifact uses its bundled ripgrep binary.

The daemon exposes no TCP port. Clients reach its Unix socket through SSH streamlocal forwarding,
matching the production topology.

## Connection

Start the container from `apps/workspace-server/`:

```bash
pnpm run run:docker-remote
```

Use these SSH connection settings in Emdash:

- Host: `localhost`
- Port: `2223`
- User: `devuser`
- Password: `devpass`

For a command-line session:

```bash
ssh -p 2223 devuser@localhost
```

The default mode is intentionally empty. Confirm that it has no host Node.js installation:

```bash
ssh -p 2223 devuser@localhost 'node --version'
# bash: node: command not found
```

This is the mode for testing OS and architecture detection, artifact pull and installation,
daemon startup, reconnects, and desktop-managed streamlocal forwarding.

## Dev Artifact Loop

For day-to-day development, build a dev-versioned Linux artifact, publish it to local minio, and
start the remote with one command:

```bash
pnpm run dev:remote
```

The script packages a Linux artifact for the host's native architecture (`linux-arm64` on Apple
Silicon, `linux-x64` otherwise), starts the Compose services (`minio`, `minio-setup`, and
`workspace-remote`), uploads the artifact layout to `http://localhost:9000/emdash-releases`, and
verifies that minio's stable and canary `workspace-server/channels/*/protocol-2.json` pointers name
the new version. Override the target with `EMDASH_WS_DEV_REMOTE_TARGET=linux-x64` or
`EMDASH_WS_DEV_REMOTE_TARGET=linux-arm64`.

The remote container is no longer recreated to ingest artifacts. It stays a bare SSH host; the
desktop provisioner resolves a minio channel pointer, then curls that version's immutable
`install.sh` with the artifact source URL pointed at minio.

When testing the desktop app interactively against this remote, launch it with:

```bash
pnpm run dev:remote-app
```

which expands to:

```bash
EMDASH_WORKSPACE_SERVER_ARTIFACTS_URL=http://minio:9000/emdash-releases/workspace-server \
  EMDASH_WORKSPACE_SERVER_DEV_AUTO_UPDATE=1 \
  pnpm --dir ../emdash-desktop run dev
```

The `minio` hostname is resolved by the `workspace-remote` container. The host can inspect the same
objects through `http://localhost:9000/emdash-releases/workspace-server/`.

`EMDASH_WORKSPACE_SERVER_DEV_AUTO_UPDATE=1` makes the desktop compare the running daemon's
`appVersion` with the artifact version in its channel pointer for the desktop protocol major. If
they differ, the desktop reinstalls that exact version and restarts the remote daemon during the next
ensure/reconnect. This is development-only; production provisioning still keeps compatible running
daemons installed until an explicit update or protocol upgrade.

## Re-publish Without Restarting Docker

After `pnpm run dev:remote` has started minio, you can rebuild and publish a specific version and
target manually. `upload:dev` defaults to the host's Linux target and uploads the newest matching
archive under `dist-artifacts/`:

```bash
EMDASH_WS_DEV_VERSION=0.1.0-dev.manual pnpm run package --target linux-arm64
pnpm run upload:dev
```

Use `EMDASH_WS_DEV_REMOTE_TARGET=linux-x64` when publishing an x64 artifact from Apple Silicon, or
pass `--version` / `--target` to override detection. With the desktop running in dev-auto-update
mode, the next ensure/reconnect sees the updated channel pointer, installs its pinned artifact
version, and restarts the daemon.

Run the desktop connection smoke test against the installed daemon:

```bash
pnpm --dir ../emdash-desktop run test:workspace-server-remote
```

The test uses the Compose service's fixed `localhost:2223` and `devuser`/`devpass` credentials. It
expects `pnpm run dev:remote` to have already published artifacts to minio, resets the
desktop-managed root, installs through the curl installer, exercises a runtime call and SSH
reconnection, then stops the daemon and removes its temporary workspace.

## Logs And Socket Forwarding

The daemon log is stored beside its socket. Follow it without opening an SSH session:

```bash
docker exec --user devuser emdash-workspace-remote \
  tail -f /home/devuser/.emdash/workspace-server/run/workspace.sock.log
```

To inspect streamlocal forwarding manually, first start the daemon, then run:

```bash
rm -f /tmp/emdash-workspace-server.sock
ssh -p 2223 -N \
  -L /tmp/emdash-workspace-server.sock:/home/devuser/.emdash/workspace-server/run/workspace.sock \
  devuser@localhost
```

While that SSH process is running, `/tmp/emdash-workspace-server.sock` is the local endpoint. The
desktop transport performs the same forwarding in-process and calls Wire `initialize` before using
runtime services.

## Reset To A Bare Machine

Stop the Compose project and delete its named volumes:

```bash
docker compose down -v
```

This removes only the workspace remote container, network, and its `emdash-workspace-remote-home`
and `emdash-workspace-minio-data` volumes. The legacy desktop `ssh-dev` Compose project and its
`projects` volume are separate. This is no longer required for normal dev artifact refreshes; use it
only when you need a bare machine, want to remove persisted daemon state, or want to clear the local
artifact bucket.

## Testing Another Architecture

The service uses the host's native Linux architecture by default. On Apple Silicon, set the
optional Compose platform to exercise the `linux-x64` artifact and architecture-detection branch
under emulation:

```bash
WORKSPACE_REMOTE_PLATFORM=linux/amd64 \
  EMDASH_WS_DEV_REMOTE_TARGET=linux-x64 \
  pnpm run dev:remote
```

Docker runs the amd64 image with its equivalent of `--platform linux/amd64`; startup is slower
than the native arm64 container.
