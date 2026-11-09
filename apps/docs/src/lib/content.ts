/**
 * The homepage's copy, which the README says too (README.md and apps/docs/README.md): the plugin's
 * description, the install commands, the agents and the features. The page renders it,
 * and so does /llms.txt (app/llms.txt/route.ts), so the two never drift apart.
 */
import { normalizeDiscordUrl } from "@/lib/github";
import { siteConfig } from "@/lib/site";

// What the plugin is: its long description, as every plugin manifest says it.
export const pluginDescription =
  "The text-to-cad plugin gives your agent local workflows for generating 3D models as STEP, GLB, STL or 3MF files. It also does design for manufacturing checks, generates engineering drawings, and connects to popular 3D printing, sheet metal and CNC fabrication services.";

// The install: one command per system, which sets up text-to-cad in every agent app on the computer
// and, run again, updates it (the README's Quickstart, which says the same, word for word).
export const installCommands = [
  { system: "macOS and Linux", language: "bash", command: "curl -fsSL https://texttocad.dev/install.sh | sh" },
  { system: "Windows, in PowerShell", language: "powershell", command: "irm https://www.texttocad.dev/install.ps1 | iex" },
];
// What the command does, and that running it again is the update, under the commands. The command
// name is in backticks, which the page sets as code.
export const installSummary =
  "It installs uv if it is missing, then sets up text-to-cad in every agent app on your computer with each app's own commands (the plugin, which brings the skills and CAD's MCP server, or for an agent without a plugin the skills alone), registers the `cad` command, and moves CAD's server to the new release. Run it again to update everything, or click CAD's update button when it shows one; it lists the apps to restart.";
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
  { name: "Hermes", logo: "nous-research" },
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
      body: "A bug report with the model script and the output of `cad doctor --check` is the fastest to fix, and an agent app without a plugin gets one on request. A security problem is reported privately, as SECURITY.md says.",
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

// What text-to-cad does, the README's Features, item for item and word for word: each one's name,
// the page that documents it (a path in the repository; every skill's folder is one of them), what it
// does, and the file its picture on the homepage shows (`FeatureArt`, components/feature-art.tsx).
export const featuresIntro = "The text-to-cad plugin gives your agent local workflows to generate 3D models as STEP, GLB, STL or 3MF files, check them for manufacturing, draw them, and connect to 3D printing, sheet metal and CNC services. It works with any agent that supports plugins or skills.";
export const features = [
  {
    id: "parts",
    name: "Parts and assemblies",
    path: "skills/cad/SKILL.md",
    summary: "Models written as Python scripts with [build123d](https://github.com/gumyr/build123d) and [OpenCASCADE](https://github.com/Open-Cascade-SAS/OCCT), exported as STEP, STL, 3MF or GLB, and as [DXF profiles and flat patterns](skills/cad/references/2d-profiles-and-dxf.md) for laser and waterjet cutting, with joints and animations for mechanisms, and shown live in the CAD viewer.",
    file: "bracket.py",
  },
  {
    id: "boards",
    name: "Circuit boards",
    path: "skills/pcb/SKILL.md",
    summary: "KiCad schematics and boards, placed and routed, checked with ERC and DRC, reviewed before you order, and exported as fabrication files.",
    file: "sensor.kicad_pcb",
  },
  {
    id: "checks",
    name: "Manufacturing checks",
    path: "skills/cad/SKILL.md#can-it-be-made",
    summary: "Whether a part can be machined, cut and bent, molded or 3D printed, measured against the process's rules, and what to change where it cannot.",
    file: "housing.step",
  },
  {
    id: "stress",
    name: "Stress checks",
    path: "skills/fea/SKILL.md",
    summary: "Whether a part or an assembly of bonded parts holds under its loads, solved with CalculiX: each part's peak stress, safety factor and how far it moves, drawn on the model.",
    file: "bracket.step",
  },
  {
    id: "drawings",
    name: "Engineering drawings",
    path: "skills/engineering-drawing/SKILL.md",
    summary: "Dimensioned PDF sheets projected from the part's geometry: views, hidden lines, centre marks, hole callouts and a title block.",
    file: "bracket.pdf",
  },
  {
    id: "fabrication",
    name: "Fabrication services",
    path: "skills/sendcutsend/SKILL.md",
    summary: "[Checks DXF and STEP files against SendCutSend's guide](skills/sendcutsend/SKILL.md) before you upload them, and [slices 3D prints](skills/print3d/SKILL.md) with OrcaSlicer and sends them to Bambu Connect or Bambu Studio.",
    file: "bracket_flat.dxf, housing.gcode.3mf",
  },
  {
    id: "robots",
    name: "Robotics and simulation",
    path: "skills/robot-simulation/SKILL.md",
    summary: "Robot and world descriptions for simulation and motion planning: URDF for ROS, SRDF for MoveIt and SDF for Gazebo.",
    file: "arm.urdf",
  },
];
