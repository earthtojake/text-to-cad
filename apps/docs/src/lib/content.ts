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
// (the README's Quickstart, which says the same, word for word).
export const installCommands = [
  { system: "macOS and Linux", language: "bash", command: "curl -fsSL https://texttocad.dev/install.sh | sh" },
  { system: "Windows, in PowerShell", language: "powershell", command: "irm https://www.texttocad.dev/install.ps1 | iex" },
];
// What the command does, under the commands. The command name is in backticks, which the page sets as
// code.
export const installSummary =
  "It installs uv if it is missing, then `cad`, the command text-to-cad runs on, then the plugin in each agent app it finds on your computer, with that app's own command (Kimi Code you install by hand), and turns on automatic updates.";
// Installing by hand, each app's own commands, updating and removing: a page in the repository (the
// README's Quickstart links it too), which the site does not repeat: the documentation shows that file as it
// is, at `page`.
export const manualInstall = { label: "Installing by hand, app by app, updating and removing", path: "docs/install.md" };
export const manualInstallPage = "/docs/install";

// The agent apps text-to-cad installs in, as docs/install.md lists them and the README names them: Claude
// Code, Codex and Cursor first. Each logo is a light glyph on a black square in public/agents/ (skills.sh's
// set, and Grok's glyph from Lobe Icons, MIT); an app with none there shows its initials in the same square.
export const agents: { name: string; logo?: string }[] = [
  { name: "Claude Code", logo: "claude-code" },
  { name: "Codex", logo: "codex" },
  { name: "Cursor", logo: "cursor" },
  { name: "Gemini", logo: "gemini" },
  { name: "Grok", logo: "grok" },
  { name: "Copilot CLI", logo: "copilot" },
  { name: "Qwen Code" },
  { name: "Droid", logo: "droid" },
  { name: "Devin" },
  { name: "Antigravity", logo: "antigravity" },
  { name: "Pi" },
  { name: "Muse" },
  { name: "Kimi Code" },
  { name: "Hermes", logo: "nous-research" },
  { name: "Cline", logo: "cline" },
  { name: "Amp", logo: "amp" },
  { name: "OpenClaw", logo: "openclaw" },
  { name: "Kilo Code", logo: "kilo" },
  { name: "Kiro CLI", logo: "kiro-cli" },
  { name: "Roo Code", logo: "roo" },
  { name: "Trae", logo: "trae" },
  { name: "Windsurf", logo: "windsurf" },
  { name: "Goose", logo: "goose" },
  { name: "OpenCode", logo: "opencode" },
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

// The projects around text-to-cad, the README's Community, item for item and word for word: the ones
// built on top of it and the ones it uses. Each one's name, what it is, and its links, side by side.
export const community = {
  intro: "Projects built on top of text-to-cad, and projects that text-to-cad uses.",
  items: [
    {
      title: "Studio",
      body: "An open-source desktop CAD app for mechanical engineers, built on text-to-cad, for Mac and Windows. You describe a part to the agent, and the 3D model, drawings, stress check and versions sit beside the chat, where you can also edit the model by hand.",
      links: [
        { text: "Website", href: "https://texttocad.studio" },
        { text: "GitHub", href: "https://github.com/amywork777/studio" },
      ],
    },
  ],
};

// What text-to-cad does, the README's Features, item for item and word for word: each one's name,
// the page that documents it (a path in the repository; every skill's folder is one of them), what it
// does, the file its picture on the homepage shows (`FeatureArt`, components/feature-art.tsx), and the
// page of the documentation's Skills, one a skill and named after it, that its tile on the homepage
// links (the README links the skill itself).
export const featuresIntro = "The text-to-cad plugin gives your agent local workflows to generate 3D models as STEP, GLB, STL or 3MF files, check them for manufacturing, draw them, and connect to 3D printing, sheet metal and CNC services. It works with any agent that supports plugins or skills.";
export const features = [
  {
    id: "parts",
    name: "Parts and assemblies",
    path: "skills/cad/SKILL.md",
    summary: "Models written as Python scripts with [build123d](https://github.com/gumyr/build123d) and [OpenCASCADE](https://github.com/Open-Cascade-SAS/OCCT), exported as STEP, STL, 3MF or GLB, and as [DXF profiles and flat patterns](skills/cad/references/2d-profiles-and-dxf.md) for laser and waterjet cutting, with joints and animations for mechanisms, and shown live in the viewer.",
    file: "bracket.py",
    page: "/docs/cad",
  },
  {
    id: "boards",
    name: "Circuit boards",
    path: "skills/pcb/SKILL.md",
    summary: "KiCad schematics and boards, placed and routed, checked with ERC and DRC, reviewed before you order, and exported as fabrication files.",
    file: "sensor.kicad_pcb",
    page: "/docs/pcb",
  },
  {
    id: "checks",
    name: "Manufacturing checks",
    path: "skills/cad/SKILL.md#can-it-be-made",
    summary: "Whether a part can be machined, cut and bent, molded or 3D printed, measured against the process's rules, and what to change where it cannot.",
    file: "housing.step",
    page: "/docs/cad#manufacturing-checks",
  },
  {
    id: "stress",
    name: "Stress checks",
    path: "skills/fea/SKILL.md",
    summary: "Whether a part or an assembly of bonded parts holds under its loads, solved with CalculiX: each part's peak stress, safety factor and how far it moves, drawn on the model.",
    file: "bracket.step",
    page: "/docs/fea",
  },
  {
    id: "drawings",
    name: "Engineering drawings",
    path: "skills/engineering-drawing/SKILL.md",
    summary: "Dimensioned PDF sheets projected from the part's geometry: views, hidden lines, centre marks, hole callouts and a title block.",
    file: "bracket.pdf",
    page: "/docs/engineering-drawing",
  },
  {
    id: "renders",
    name: "Renders",
    path: "skills/render/SKILL.md",
    summary: "Photoreal stills, turntables and films of a model with Blender, lit and framed in a Python script and run on the GPU, with a quick draft before each final.",
    file: "hero.png, turntable.mp4",
    page: "/docs/render",
  },
  {
    id: "fabrication",
    name: "Fabrication services",
    path: "skills/sendcutsend/SKILL.md",
    summary: "[Checks DXF and STEP files against SendCutSend's guide](skills/sendcutsend/SKILL.md) before you upload them, and [slices 3D prints](skills/print3d/SKILL.md) with OrcaSlicer and sends them to Bambu Connect or Bambu Studio.",
    file: "bracket_flat.dxf, housing.gcode.3mf",
    page: "/docs/sendcutsend",
  },
  {
    id: "robots",
    name: "Robotics and simulation",
    path: "skills/robot-simulation/SKILL.md",
    summary: "Robot and world descriptions for simulation and motion planning: URDF for ROS, SRDF for MoveIt and MJCF for MuJoCo.",
    file: "arm.urdf",
    page: "/docs/robot-simulation",
  },
];
