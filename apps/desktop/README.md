# Hardcore desktop (`apps/desktop`)

Hardcore is the CAD-first desktop workspace for Text-to-CAD: threads of Claude or Codex work beside
the CAD Viewer, and accepted STEP files are the canonical artifacts. It lives here, inside the
Text-to-CAD monorepo, so it always builds against the repository's own `apps/viewer`,
`packages/cadgen`, `packages/cadgen-js`, and `skills/`.

This directory is a self-contained pnpm workspace (its own `package.json`, `pnpm-workspace.yaml`,
lockfile, and internal `@emdash/*` packages) so installing the CAD skills never pulls in Electron. The
Electron app itself is `apps/emdash-desktop/`; see `AGENTS.md` for the layout and
`agents/integrations/cad.md` for how the app uses the canonical Text-to-CAD resources.

## Product model

- An engineering project owns parts, assemblies, drawings, and project discussions.
- Each thread owns its conversation and the artifacts it opens; many threads run in parallel.
- The on-disk STEP and its hash are the canonical model state; a plain `.py` `@step` recipe is its
  optional source, edited in the general source editor and rebuilt through cadgen's own script door.
- Jake's CAD Viewer owns everything inside the viewport; the desktop owns the artifact lifecycle.

## Development

Prerequisites: any `pnpm` (the pinned Node and pnpm are provisioned from `package.json`), Python
3.11+, and `npm` for the one-time CAD Viewer client build. From this directory:

```bash
pnpm install
pnpm cad:setup      # Python runtime, apps/viewer/dist, and the cad@text-to-cad provider plugin
pnpm run dev
```

`pnpm cad:setup` accepts a repository `.venv` that already imports cadgen from `packages/cadgen`
(the CONTRIBUTING setup at the repository root); otherwise it provisions a managed runtime under the
app's user data.

Quality gates, also from this directory:

```bash
pnpm run check      # format, lint, typecheck, test
pnpm cad:check      # report the CAD runtime, viewer client, and provider plugins
pnpm cad:test       # Jake's selected suites, the viewer launch smoke, and a generate/validate smoke
```

Packaging (`pnpm --dir apps/emdash-desktop run package:mac`) bundles the built viewer, the skills,
`packages/cadgen`, and the runtime installer under `Contents/Resources/text-to-cad`; the packaged CAD
smoke (`scripts/release/verify-packaged-cad.ts`) provisions that bundle in a scratch directory and
exercises two isolated project roots.

## Privacy

Hardcore is local-first. App state, engineering files, and conversation metadata are stored on the
machine. Claude and Codex may send prompts and selected context to their respective providers.
Telemetry is optional and can be disabled in Settings or with:

```bash
TELEMETRY_ENABLED=false
```

## License

Licensed under the [Apache-2.0 license](LICENSE.md).

Built-in issue-tracker connectors and issue search are intentionally omitted from the CAD app.
GitHub sign-in, Git source control, and pull-request review remain available for model recipes.
Configured MCP tools can supply external context. Existing saved issue references and database
migration history are retained for compatibility; the desktop no longer contacts those trackers.

Scheduled agent automations and web development server previews are also omitted. This removes
scheduler workers, cron dependencies, terminal URL scanning, port probes, and automatic preview
tunnels. Historical automation records and migrations remain readable; no scheduler is started.
CAD preview still uses the canonical cadgen outputs and viewer.

The Codex and Claude model pickers discover models through the installed provider's ACP adapter.
Open the picker or choose Refresh to retrieve the provider's current catalog, including new model
IDs. Choices depend on provider authentication and settings; keep the provider CLI up to date.
Discovery initializes a short-lived session without sending a prompt, then releases its process.

Remote workspaces require the matching protocol 3 workspace-server build. Protocol 2 servers are
rejected during negotiation because scheduled automations and preview-server streams were removed.

The desktop has no hosted app account or sign-in gate. GitHub connections use the local
GitHub CLI or GitHub device flow from settings; agent authentication stays with each
provider CLI. First run opens the welcome screen directly. Existing Hardcore projects and chats
continue through the normal database migrations.
