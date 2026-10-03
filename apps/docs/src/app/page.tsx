import { ExternalLink } from "lucide-react";
import Image from "next/image";
import { CopyButton } from "@/components/copy-button";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { absoluteUrl, siteConfig } from "@/lib/site";

// What the plugin is: its long description, as every plugin manifest says it.
const pluginDescription =
  "The text-to-cad plugin gives your agent local workflows for generating 3D models as STEP, GLB, STL or 3MF files. It also does design for manufacturing checks, generates engineering drawings, and connects to popular 3D printing, sheet metal and CNC fabrication services.";

// The install: a message for the agent, which finds the install for its own app in the repository
// (the README's Install, which says the same).
const agentInstallMessage = "Install text-to-cad from https://github.com/earthtojake/text-to-cad";

// Installing by hand, each its own sub-section of Install: the plugin for each agent app (the skills
// and CAD's viewer together), then the skills alone, with the Skills CLI, for any other agent.
const installs = [
  {
    id: "claude-code",
    agent: "Claude Code",
    command:
      "claude plugin marketplace add earthtojake/text-to-cad\nclaude plugin install text-to-cad@earthtojake",
  },
  {
    id: "codex",
    agent: "Codex",
    note: "Requires Codex 0.142.0 or newer.",
    command:
      "codex plugin marketplace add earthtojake/text-to-cad\ncodex plugin add text-to-cad@earthtojake",
  },
  {
    id: "cursor",
    agent: "Cursor",
    note: "Cursor also loads the Claude Code plugin: install one or the other.",
    command:
      "git clone --depth 1 https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad",
  },
  // Grok Build reads the Claude plugin manifest -- there is no separate Grok manifest -- and
  // installs straight from the repo rather than adding a marketplace first.
  {
    id: "grok-build",
    agent: "Grok Build",
    note: "Grok Build also loads the Claude Code plugin: install one or the other.",
    command: "grok plugin install earthtojake/text-to-cad --trust\ngrok plugin enable text-to-cad",
  },
  {
    id: "gemini",
    agent: "Gemini",
    command: "gemini extensions install https://github.com/earthtojake/text-to-cad",
  },
  {
    id: "other-agents",
    agent: "Other Agents",
    note: "For an agent without plugin support: the skills give you everything you need for core CAD workflows and let you view CAD files in a localhost web app.",
    command: "npx skills add earthtojake/text-to-cad",
  },
];

// The agents text-to-cad installs into, as skills.sh shows them (its logos, in public/agents/), and
// Grok (Lobe Icons' glyph, MIT, in skills.sh's tile). A logo leads to its install: its plugin's
// where the agent has one, the skills alone (Other Agents) where it has none.
const agents = [
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
const pluginRequestUrl = `${siteConfig.repository}/issues/new?title=${encodeURIComponent("Plugin request: ")}`;

const skillGroups = [
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

const COMMAND_BOX_CLASS =
  "min-w-0 w-full overflow-hidden rounded-lg border border-border bg-card shadow-xs";

function AgentMessage() {
  return (
    <div className={COMMAND_BOX_CLASS}>
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <p className="flex min-w-0 flex-1 items-center px-3 py-2 text-sm leading-6 text-foreground">
          {agentInstallMessage}
        </p>
        <CopyButton text={agentInstallMessage} label="Copy the message for your agent" prominent />
      </div>
    </div>
  );
}

// The agents' logos, scrolling as skills.sh's do: two copies side by side, moved one copy's width
// and over again, paused under the pointer, and still for anyone who asks for less motion. Each
// tile is a black square: it takes the page's own colour, lightened into the dark theme and, inverted,
// darkened into the light one. The track keeps the page's background behind it to blend with.
function AgentCarousel() {
  const logos = (copy: number) => (
    <ul className={copy ? "flex shrink-0 motion-reduce:hidden" : "flex shrink-0"} aria-hidden={copy ? true : undefined}>
      {agents.map((agent) => (
        <li key={agent.logo}>
          <a href={`#${agent.install}`} title={`Install text-to-cad for ${agent.name}`} tabIndex={copy ? -1 : undefined}>
            <Image
              src={`/agents/${agent.logo}.svg`}
              alt={agent.name}
              width={100}
              height={100}
              unoptimized
              className="h-[72px] w-auto invert mix-blend-darken lg:h-[88px] dark:invert-0 dark:mix-blend-lighten"
            />
          </a>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)] motion-reduce:overflow-x-auto">
        <div className="flex w-max animate-[agents-carousel_110s_linear_infinite] bg-background hover:[animation-play-state:paused] motion-reduce:animate-none">
          {logos(0)}
          {logos(1)}
        </div>
      </div>
  );
}

function Install({ item }: { item: (typeof installs)[number] }) {
  return (
    <div id={item.id} className="min-w-0 scroll-mt-20 space-y-2">
      <div>
        <h3 className="text-base font-semibold text-foreground">{item.agent}</h3>
        {item.note ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.note}</p> : null}
      </div>
      <div className={COMMAND_BOX_CLASS}>
        <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
          <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre font-mono px-3 py-2 text-sm leading-6 text-foreground">
            {item.command}
          </code>
          <CopyButton text={item.command} label={`Copy the ${item.agent} install command`} />
        </div>
      </div>
    </div>
  );
}

function SectionIntro({
  id,
  title,
  description,
}: {
  id?: string;
  title: string;
  description?: string;
}) {
  return (
    <div>
      <h2
        id={id}
        className="text-heading font-semibold tracking-tight text-foreground"
      >
        {title}
      </h2>
      {description ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {description}
        </p>
      ) : null}
    </div>
  );
}

function SkillLink({ skill }: { skill: (typeof skillGroups)[number] }) {
  return (
    <a
      className="inline-flex min-w-0 items-center gap-1.5 font-mono text-xs text-muted-foreground transition hover:text-foreground"
      href={`https://github.com/earthtojake/text-to-cad/blob/main/${skill.path}/SKILL.md`}
      target="_blank"
      rel="noreferrer"
    >
      <span className="truncate">{skill.path}</span>
      <ExternalLink className="size-3 shrink-0" />
    </a>
  );
}

// What search engines read about the project: the site, and the free, open-source software it is.
const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": absoluteUrl("/#website"),
      name: siteConfig.name,
      url: absoluteUrl("/"),
      description: siteConfig.description,
    },
    {
      "@type": "SoftwareApplication",
      name: siteConfig.name,
      url: absoluteUrl("/"),
      description: siteConfig.description,
      applicationCategory: "DesignApplication",
      operatingSystem: "macOS, Windows, Linux",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      license: "https://opensource.org/licenses/MIT",
      image: absoluteUrl("/social-preview.png"),
      sameAs: [siteConfig.repository],
      author: { "@type": "Person", name: siteConfig.author.name, url: siteConfig.author.url },
    },
  ],
};

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        // JSON, with `<` escaped so nothing in it can close the script tag.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
      <SiteHeader heroWordmark />

      <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
        <div className="min-w-0 space-y-2">
          <HeroSection />

          <section id="overview" aria-labelledby="overview-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro id="overview-title" title="Overview" />
            {/* First, so a phone shows the agents on load, under the hero. */}
            <div>
              <h3 className="text-base font-semibold text-foreground">Available for these agents</h3>
              <AgentCarousel />
            </div>
            <p className="text-sm leading-6 text-muted-foreground">{pluginDescription}</p>
            <p className="text-sm leading-6 text-muted-foreground">
              It is supported by all popular agents that support plugins or the{" "}
              <a href="https://skills.sh" target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
                skills
              </a>{" "}
              framework, including Claude Code, Codex, Cursor, Gemini and Grok.
            </p>
          </section>

          <section id="installation" aria-labelledby="installation-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro
              id="installation-title"
              title="Install"
              description="Send this message to your agent and it will install text-to-cad for you."
            />
            <AgentMessage />
            <div className="space-y-6 pt-6">
              <p className="text-sm leading-6 text-muted-foreground">
                Or install it yourself. The plugin brings the skills and CAD&apos;s viewer, a local server that
                runs through uv, which must be installed. Restart your agent if newly installed skills do not
                appear.
              </p>
              {installs.map((item) => (
                <Install key={item.agent} item={item} />
              ))}
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm leading-6 text-muted-foreground">No plugin for your agent yet?</p>
                <Button asChild variant="outline" size="sm">
                  <a href={pluginRequestUrl} target="_blank" rel="noreferrer">Request Plugin</a>
                </Button>
              </div>
            </div>
          </section>

          <section
            id="skills"
            aria-labelledby="skills-title"
            className="scroll-mt-20 space-y-3 py-6"
          >
            <SectionIntro
              id="skills-title"
              title="Skills"
              description="Install the library to give agents focused workflows for CAD, fabrication, robot description files, simulation, and local review."
            />

            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="grid grid-cols-[minmax(0,1fr)] border-b border-border px-3.5 py-2.5 text-xs font-medium text-muted-foreground md:grid-cols-[minmax(9rem,12rem)_minmax(0,1fr)_max-content] md:gap-5 md:pl-0 md:pr-3.5">
                <span className="md:pl-3.5">Skill</span>
                <span className="hidden md:block">Summary</span>
                <span className="hidden text-right md:block">Source</span>
              </div>
              <ul className="divide-y divide-border">
                {skillGroups.map((skill) => (
                  <li
                    key={skill.name}
                    className="grid transition-colors gap-3 px-3.5 py-3 hover:bg-secondary/60 md:grid-cols-[minmax(9rem,12rem)_minmax(0,1fr)_max-content] md:items-center md:gap-5 md:pl-0 md:pr-3.5"
                  >
                    <div className="flex min-w-0 items-center md:pl-3.5">
                      <div className="min-w-0">
                        <h3 className="text-sm font-medium text-foreground">
                          {skill.name}
                        </h3>
                        <p className="mt-0.5 text-xs font-mono text-muted-foreground md:hidden">
                          {skill.path}
                        </p>
                      </div>
                    </div>
                    <div className="min-w-0 text-sm leading-6 text-muted-foreground">
                      <p>{skill.summary}</p>
                    </div>
                    <div className="min-w-0 md:justify-self-end md:pt-0.5 md:text-right">
                      <SkillLink skill={skill} />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </section>

        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
