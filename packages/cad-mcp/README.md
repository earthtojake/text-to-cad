# cad-mcp

The stdio transport an agent app starts for text-to-cad's CAD app (`cad-mcp`): it carries the app's MCP
requests to the CAD server on this computer, over HTTP, and the server's answers back. The standard
library alone, imported as `cad_mcp`.

It holds no tool, view or document: the server does. What it does on its own:

- **Is one version on one channel.** Its version is its own package's release (a development install names
  its build in `CAD_INSTALLATION_VERSION`); its channel is `--channel NAME` in the app's server config that
  starts it, none for the default channel (`cad-mcp --channel codex`), as a store's builder writes it into the
  copy that store delivers. Nothing in its environment names a channel: `CAD_INSTALL_CHANNEL` and
  `CAD_AUTO_UPDATED`, which configs of 0.11.10 and earlier set, are not read. The server counts each session's
  use under that channel and the app its `initialize` names.
- **Makes its version ready as it starts**, in the background, outside any sandbox: installed where it is
  not, as the `cad` command installs one (`uvx --from cad-server==<version> cad setup --add --quiet`); then,
  where its channel's pointer in the state folder does not name it, that version's own `cad` run pinned to it
  (`cad +<version>[@<channel>] setup --add --quiet`), which moves the channel to it, or finds the channel past
  it. The app's `initialize` waits for this at most 20 seconds, inside Codex's start window: past that it is
  answered here and the server's session opened at the next request.
- **Reaches its own version's server** alone, the way every client of that version does: through its door,
  `<version>` in the engine folder, which names the server's HTTP endpoint and token, and starts that
  version's server when none answers, never another's.
- **Says a thread is stale**: once its channel's pointer names another version (an update moved the channel
  while the app's thread stayed open), every tool call is answered with one line saying so, and to start a
  new thread.
- **From a source tree** (a checkout, which has no version) it reaches the server as every transport of 0.11.10
  and earlier does: the flat door, the current installation's server (`installations/current`), and on a
  computer with none, the one its environment carries registered first, else its own release's installed by
  `uvx`.
- **Holds the server** while the app runs, under a name its sessions are opened by, which end when the
  app quits.
- **Opens the person's browser** where a text-only app's `cad_show` asks, in the app's own environment,
  never in the server's, and tells the server whether it opened.
- **Says which app started it**, read from its parent processes, which only it can see.
- **Says when Claude Code started it**: `CLAUDE_CODE_ENTRYPOINT`, which Claude Code sets for every server
  it starts, in its terminal and in the Claude desktop app's Code tab, goes to the server with the host's
  `initialize`, and that session lists no tools: there CAD is the cad skill and the `cad` command. A server
  someone added to Claude Desktop's own config by hand never sees the variable, and keeps every tool.
  `CAD_MCP_CARDS=1` in this process's environment keeps the tools, for testing.
