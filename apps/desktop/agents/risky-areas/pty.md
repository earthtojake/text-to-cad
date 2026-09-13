# Risky Area: PTY And Sessions

## Main Files

- `packages/core/src/services/pty/` — terminal env construction, shell resolution, spawning, and session registry
- `packages/core/src/runtimes/terminals/` — interactive terminal lifecycle and Wire component
- `packages/core/src/runtimes/scripts/` — lifecycle script execution through the shared PTY plane
- `packages/core/src/runtimes/tui-agents/` — PTY-backed agent sessions, runtime-owned hook server, hook installation, and agent state LiveModels
- `src/main/core/agent-status/` — desktop projection of runtime agent states into the conversation cache
- `src/services/notifications/` — desktop notification feed, batching, sound sink, and OS notification sink

## Core Risks

- PTY cleanup and exit handling
- resize behavior
- shell quoting and Windows command wrapping
- tmux lifecycle
- provider-specific resume/session behavior
- env passthrough safety

## Rules

- construct every PTY environment through `packages/core/src/services/pty/api/terminal-env.ts`
- keep the host/worker `process.env` separate from the captured user-shell environment; only the
  host process captures it, spawning runtimes receive a parent-owned source and resolve that source
  exactly once per spawn, never as an ambient fallback or immutable worker config
- do not weaken quoting or spawn behavior casually
- validate both direct spawn and shell-wrapped spawn cases when changing PTY startup logic
- confirm renderer event flow if hook/plugin payload or agent status behavior changes
