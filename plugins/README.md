# Plugins

This directory contains plugin packages for production agent installs. Local
development should link the source skills directly, as described in
`CONTRIBUTING.md`.

## CAD

`plugins/cad` is the first plugin package. Its canonical release version lives
in `plugins/cad/VERSION`, and it bundles every supported CAD Skills skill as a
generated production copy of the canonical `skills/` directories.

The plugin is intentionally thin:

- `.codex-plugin/marketplace.json` describes the Codex marketplace package
  list for repo-root installs.
- `.claude-plugin/marketplace.json` describes the Claude Code marketplace
  package list for repo-root installs.
- `plugins/cad/.codex-plugin/plugin.json` describes the Codex plugin.
- `plugins/cad/.claude-plugin/plugin.json` describes the Claude Code plugin.
- `plugins/cad/VERSION` records the package version.
- `plugins/cad/skills/` is a generated production copy of the root `skills/`
  sources. Refresh it with `scripts/bundle/bundle-plugin.sh`.

## Provider Support

The `cad` plugin currently has native provider manifests for:

- Codex: `plugins/cad/.codex-plugin/plugin.json`
- Claude Code: `plugins/cad/.claude-plugin/plugin.json`
