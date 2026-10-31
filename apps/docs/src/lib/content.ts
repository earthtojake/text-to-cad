/**
 * The homepage's copy, which the README says too (README.md and apps/docs/README.md): the plugin's
 * description, how it works, the install commands, the agents and the skills. The page renders it,
 * and so does /llms.txt (app/llms.txt/route.ts), so the two never drift apart.
 */
import { normalizeDiscordUrl } from "@/lib/github";
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

// How a model is made, under the overview: the README's How it works, step for step. Code is in
// backticks, which the page sets as code.
export const howItWorks = [
  "Your agent writes each model as a Python script with build123d, built on Open CASCADE.",
  "Running the script, `python model.py`, builds the model with cadgen's engine into an `.xbf` document (its parts, names, colours, materials and joints) and the STEP, GLB, STL or 3MF files the script declares. The engine keeps each model's work in memory, so an edit rebuilds only what it changed.",
  "The CAD viewer shows the model in your agent app or your browser, and follows every rebuild.",
];

// The install: one command per system, which sets up text-to-cad in every agent app on the computer
// and, run again, updates it (the README's Quickstart, which says the same, word for word).
export const installCommands = [
  { system: "macOS and Linux", language: "bash", command: "curl -fsSL https://texttocad.dev/install.sh | sh" },
  { system: "Windows, in PowerShell", language: "powershell", command: "irm https://www.texttocad.dev/install.ps1 | iex" },
];
// What the command does, and that running it again is the update, under the commands. The command
// name is in backticks, which the page sets as code.
export const installSummary =
  "It installs uv if it is missing, then sets up text-to-cad in every agent app on your computer with each app's own commands (the plugin, which brings the skills and CAD's MCP server, or for an agent without a plugin the skills alone), registers the `cad` command, and moves CAD's engine to the new release. Run it again to update everything, or click CAD's update button when it shows one; it lists the apps to restart.";
// Installing by hand, each app's own commands, and updates: a page in the repository (the README's
// Quickstart links it too), which the site does not repeat.
export const manualInstall = { label: "Installing by hand, app by app, and updates", path: "docs/install.md" };

// The agents text-to-cad works with, as skills.sh shows them (its logos, in public/agents/), and
// Grok (Lobe Icons' glyph, MIT, in skills.sh's tile).
export const agents = [
  { name: "Claude Code", logo: "claude-code" },
  { name: "Codex", logo: "codex" },
  { name: "Cursor", logo: "cursor" },
  { name: "Gemini", logo: "gemini" },
  { name: "Grok", logo: "grok" },
  { name: "GitHub Copilot", logo: "copilot" },
  { name: "Windsurf", logo: "windsurf" },
  { name: "Cline", logo: "cline" },
  { name: "AMP", logo: "amp" },
  { name: "Antigravity", logo: "antigravity" },
  { name: "OpenClaw", logo: "openclaw" },
  { name: "Droid", logo: "droid" },
  { name: "Goose", logo: "goose" },
  { name: "Kilo", logo: "kilo" },
  { name: "Kiro CLI", logo: "kiro-cli" },
  { name: "Nous Research", logo: "nous-research" },
  { name: "OpenCode", logo: "opencode" },
  { name: "Roo", logo: "roo" },
  { name: "Trae", logo: "trae" },
  { name: "VS Code", logo: "vscode" },
  { name: "Zed", logo: "zed" },
];

// A plugin for an agent that has none: a new issue, titled for the person to name it.
export const pluginRequestUrl = `${siteConfig.repository}/issues/new?title=${encodeURIComponent("Plugin request: ")}`;

// How to take part, the README's Contributing in substance: each way in, with its links. Code is in
// backticks, which the page sets as code.
export const contributing = {
  intro: "text-to-cad is MIT-licensed and built in the open.",
  items: [
    {
      title: "Bugs and plugin requests",
      body: "A bug report with the model script and the output of `cad doctor` is the fastest to fix, and an agent app without a plugin gets one on request. A security problem is reported privately, as SECURITY.md says.",
      links: [
        { text: "Open an issue", href: `${siteConfig.repository}/issues/new` },
        { text: "Request a plugin", href: pluginRequestUrl },
        { text: "SECURITY.md", href: `${siteConfig.repository}/blob/main/SECURITY.md` },
      ],
    },
    {
      title: "Questions, ideas and what you made",
      body: "Say what the skills got wrong, too: that is what improves them.",
      links: [{ text: "Join the Discord", href: normalizeDiscordUrl() }],
    },
    {
      title: "Code, skills and models",
      body: "A new skill (a fabrication service, a printer, a CAD workflow) goes in `skills/`, an example model in `models/`, and fixes anywhere. The contributing guide has the local setup and how to test in the agent apps.",
      links: [{ text: "Contributing guide", href: `${siteConfig.repository}/blob/main/CONTRIBUTING.md` }],
    },
  ],
};

export const skillGroups = [
  {
    name: "CAD",
    path: "skills/cad",
    summary:
      "Creates and edits CAD models from plain-language or image requests as Python scripts, built into XBF documents with STEP, STL, 3MF and GLB exports.",
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
