# cad-mcp

The stdio transport an agent app starts for text-to-cad's CAD app (`cad-mcp`): it carries the app's MCP
requests to the CAD server on this computer, over HTTP, and the server's answers back. The standard
library alone, imported as `cad_mcp`.

It holds no tool, view or document: the server does. What it does on its own:

- **Reaches the server** the way every client does: through the server's door in its folder, which names
  the server's HTTP endpoint and token. When none answers, it starts the current installation's server
  (`installations/current` in the user's state folder), whatever release it is itself.
- **Registers one first** on a computer with no installation current: the server its own environment
  carries, else the server of its own release, installed by `uvx`.
- **Holds the server** while the app runs, under a name its sessions are opened by, which end when the
  app quits.
- **Opens the person's browser** where a text-only app's `cad_show` asks, in the app's own environment,
  never in the server's, and tells the server whether it opened.
- **Says which app started it**, read from its parent processes, which only it can see.
- **Says when Claude Code started it**: `CLAUDE_CODE_ENTRYPOINT`, which Claude Code sets for every server
  it starts, in its terminal and in the Claude desktop app's Code tab, goes to the server with the host's
  `initialize`, and that session lists no tools: there CAD is the cad skill and the `cad` command, and the
  Code tab's card comes from Claude Desktop's own config, whose server Claude Code does not start and which
  never sees the variable. `CAD_MCP_CARDS=1` in this process's environment keeps the tools, for testing.
