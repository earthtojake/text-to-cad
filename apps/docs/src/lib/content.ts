/**
 * The homepage's copy, which the README says too (README.md and apps/docs/README.md): the plugin's
 * description, the install message, the installs, the agents and the skills. The page renders it,
 * and so does /llms.txt (app/llms.txt/route.ts), so the two never drift apart.
 */
import { siteConfig } from "@/lib/site";

// What the plugin is: its long description, as every plugin manifest says it.
export const pluginDescription =
  "The text-to-cad plugin gives your agent local workflows for generating 3D models as STEP, GLB, STL or 3MF files. It also does design for manufacturing checks, generates engineering drawings, and connects to popular 3D printing, sheet metal and CNC fabrication services.";

// Who it is for: the sentence after the description, the skills framework linked.
export const support = {
  before: "It is supported by all popular agents that support plugins or the",
  link: { text: "skills", href: "https://skills.sh" },
  after: "framework, including Claude Code, Codex, Cursor, Gemini and Grok.",
};

// The install: a message for the agent, which finds the install for its own app in the repository
// (the README's Install, which says the same).
export const agentInstallByline = "Send this message to your agent and it will install text-to-cad for you.";
export const agentInstallMessage = "Install text-to-cad from https://github.com/earthtojake/text-to-cad";
// The same message, opened in an agent app with its composer prefilled, never sent: Claude Code in
// Claude Desktop (claude://code/new, Claude's help center, "Open Claude Desktop with a link"), the
// Codex app (codex://threads/new, its commands reference) and Cursor (its prompt deeplink, Cursor's
// docs, "Deeplinks"). By install id, for the logo.
export const agentInstallLinks = [
  { id: "claude-code", agent: "Claude Code", href: `claude://code/new?q=${encodeURIComponent(agentInstallMessage)}` },
  { id: "codex", agent: "Codex", href: `codex://threads/new?prompt=${encodeURIComponent(agentInstallMessage)}` },
  { id: "cursor", agent: "Cursor", href: `cursor://anysphere.cursor-deeplink/prompt?text=${encodeURIComponent(agentInstallMessage)}` },
];

// Installing by hand, each its own sub-section of Install: the plugin for each agent app (the skills
// and CAD's viewer together), then the skills alone, with the Skills CLI, for any other agent. Each
// plugin says how to update it (then a restart) and how to remove it, to install it again: a
// reinstall. The Skills CLI's install is its update and its reinstall, so it says neither. An app
// with a listing in its own plugin directory (`listing`) leads with that, the commands folded under
// Manual install.
export const installs = [
  {
    id: "claude-code",
    agent: "Claude Code",
    command:
      "claude plugin marketplace add earthtojake/text-to-cad#latest\nclaude plugin install text-to-cad@earthtojake",
    update: "claude plugin marketplace update earthtojake\nclaude plugin update text-to-cad@earthtojake",
    remove: "claude plugin uninstall text-to-cad@earthtojake\nclaude plugin marketplace remove earthtojake",
  },
  {
    id: "codex",
    agent: "Codex",
    listing: {
      label: "Install in Codex",
      href: "https://chatgpt.com/plugins/plugins_6ac09476ef008191a35887b22b0d048a",
    },
    command:
      "codex plugin marketplace add earthtojake/text-to-cad --ref latest\ncodex plugin add text-to-cad@earthtojake",
    update: "codex plugin marketplace upgrade earthtojake",
    remove: "codex plugin remove text-to-cad@earthtojake\ncodex plugin marketplace remove earthtojake",
  },
  {
    id: "cursor",
    agent: "Cursor",
    note: "Cursor also loads the Claude Code plugin: if it is installed, skip this.",
    command:
      "git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad",
    update: "git -C ~/.cursor/plugins/local/text-to-cad pull",
    remove: "rm -rf ~/.cursor/plugins/local/text-to-cad",
  },
  // Grok Build reads the Claude plugin manifest -- there is no separate Grok manifest -- and
  // installs straight from the repo rather than adding a marketplace first.
  {
    id: "grok-build",
    agent: "Grok Build",
    note: "Grok Build also loads the Claude Code plugin: if it is installed, skip this.",
    command: "grok plugin install earthtojake/text-to-cad@latest --trust\ngrok plugin enable text-to-cad",
    update: "grok plugin update text-to-cad",
    remove: "grok plugin uninstall text-to-cad",
  },
  {
    id: "gemini",
    agent: "Gemini",
    command: "gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent --auto-update",
    update: "gemini extensions update text-to-cad",
    remove: "gemini extensions uninstall text-to-cad",
  },
  {
    id: "other-agents",
    agent: "Other Agents",
    note: "For an agent without plugin support: the skills give you everything you need for core CAD workflows and let you view CAD files in a localhost web app.",
    command: "npx skills add earthtojake/text-to-cad#latest",
  },
];

// The agents text-to-cad installs into, as skills.sh shows them (its logos, in public/agents/), and
// Grok (Lobe Icons' glyph, MIT, in skills.sh's tile). A logo leads to its install: its plugin's
// where the agent has one, the skills alone (Other Agents) where it has none.
export const agents = [
  { name: "Claude Code", logo: "claude-code", install: "claude-code" },
  { name: "Codex", logo: "codex", install: "codex" },
  { name: "Cursor", logo: "cursor", install: "cursor" },
  { name: "Gemini", logo: "gemini", install: "gemini" },
  { name: "Grok", logo: "grok", install: "grok-build" },
  { name: "GitHub Copilot", logo: "copilot", install: "other-agents" },
  { name: "Windsurf", logo: "windsurf", install: "other-agents" },
  { name: "Cline", logo: "cline", install: "other-agents" },
  { name: "AMP", logo: "amp", install: "other-agents" },
  { name: "Antigravity", logo: "antigravity", install: "other-agents" },
  { name: "OpenClaw", logo: "openclaw", install: "other-agents" },
  { name: "Droid", logo: "droid", install: "other-agents" },
  { name: "Goose", logo: "goose", install: "other-agents" },
  { name: "Kilo", logo: "kilo", install: "other-agents" },
  { name: "Kiro CLI", logo: "kiro-cli", install: "other-agents" },
  { name: "Nous Research", logo: "nous-research", install: "other-agents" },
  { name: "OpenCode", logo: "opencode", install: "other-agents" },
  { name: "Roo", logo: "roo", install: "other-agents" },
  { name: "Trae", logo: "trae", install: "other-agents" },
  { name: "VS Code", logo: "vscode", install: "other-agents" },
  { name: "Zed", logo: "zed", install: "other-agents" },
];

// A plugin for an agent that has none: a new issue, titled for the person to name it.
export const pluginRequestUrl = `${siteConfig.repository}/issues/new?title=${encodeURIComponent("Plugin request: ")}`;

export const skillGroups = [
  {
    name: "CAD",
    path: "skills/cad",
    summary:
      "Creates and edits CAD models from plain-language or image requests, with STEP as the main output along with options to export to STL, 3MF and GLB.",
  },
  {
    name: "step.parts",
    path: "skills/step-parts",
    summary:
      "Finds off-the-shelf STEP parts like screws, bearings, motors, and connectors.",
  },
  {
    name: "Engineering Drawing",
    path: "skills/engineering-drawing",
    summary:
      "Dimensioned engineering drawings from a part, as a PDF: views, hidden lines, dimensions, hole callouts, title block.",
  },
  {
    name: "DXF",
    path: "skills/dxf",
    summary:
      "Creates 2D DXF drawings like profiles, templates, gaskets, and cut layouts from Python sources or CAD geometry.",
  },
  {
    name: "URDF",
    path: "skills/urdf",
    summary:
      "Writes robot structure files with links, joints, limits, inertials, and meshes.",
  },
  {
    name: "SRDF",
    path: "skills/srdf",
    summary:
      "Adds MoveIt planning groups, end effectors, poses, and collision rules to a URDF.",
  },
  {
    name: "SDF",
    path: "skills/sdf",
    summary:
      "Creates simulator models and worlds with frames, physics, sensors, and lights.",
  },
  {
    name: "SendCutSend",
    path: "skills/sendcutsend",
    summary: "Checks DXF and STEP files before upload to SendCutSend.",
  },
  {
    name: "DfAM Check",
    path: "skills/dfam-check",
    summary:
      "Measures mesh printability per process: wall thickness, overhangs, support volume, and build orientation.",
  },
  {
    name: "DFM",
    path: "skills/dfm",
    summary:
      "Reviews a part for sheet metal, CNC machining, or injection molding, with measured evidence and the cited rule behind every finding.",
  },
  {
    name: "G-code",
    path: "skills/gcode",
    summary:
      "Slices models into printer-ready G-code with OrcaSlicer, using your own printer presets.",
  },
  {
    name: "Bambu Labs",
    path: "skills/bambu-labs",
    summary:
      "Sends prints to Bambu Lab printers through Bambu Connect, Bambu Lab's official app, or Bambu Studio.",
  },
];
