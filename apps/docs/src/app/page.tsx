import { ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/copy-button";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { absoluteUrl, siteConfig } from "@/lib/site";

// The quickest start: a message for the agent, which reads the README's install steps and takes
// the one for its own app. The README's Get Started says the same.
const agentInstallMessage =
  "Install text-to-cad for this agent app from https://github.com/earthtojake/text-to-cad: follow the Install section of its README, using this app's plugin if it has one and the Skills CLI if not.";

// Installing by hand, each its own sub-section: the plugin for each agent app (the skills and CAD's
// viewer together), then the Skills CLI for an agent without one.
const installs = [
  {
    agent: "Claude Code",
    command:
      "claude plugin marketplace add earthtojake/text-to-cad\nclaude plugin install text-to-cad@earthtojake",
  },
  {
    agent: "Codex",
    note: "Requires Codex 0.142.0 or newer.",
    command:
      "codex plugin marketplace add earthtojake/text-to-cad\ncodex plugin add text-to-cad@earthtojake",
  },
  {
    agent: "Cursor",
    note: "Cursor also loads the Claude Code plugin: install one or the other.",
    command:
      "git clone --depth 1 https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad",
  },
  // Grok Build reads the Claude plugin manifest -- there is no separate Grok manifest -- and
  // installs straight from the repo rather than adding a marketplace first.
  {
    agent: "Grok Build",
    note: "Grok Build also loads the Claude Code plugin: install one or the other.",
    command: "grok plugin install earthtojake/text-to-cad --trust\ngrok plugin enable text-to-cad",
  },
  {
    agent: "Gemini CLI",
    command: "gemini extensions install https://github.com/earthtojake/text-to-cad",
  },
  {
    agent: "Skills CLI",
    note: "For an agent without a plugin: the skills alone.",
    command: "npx skills add earthtojake/text-to-cad",
  },
];

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
        <CopyButton text={agentInstallMessage} label="Copy the message for your agent" prominent compact />
      </div>
    </div>
  );
}

function Install({ item }: { item: (typeof installs)[number] }) {
  return (
    <div className="min-w-0 space-y-2">
      <div>
        <h3 className="text-sm font-medium text-foreground">{item.agent}</h3>
        {item.note ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.note}</p> : null}
      </div>
      <div className={COMMAND_BOX_CLASS}>
        <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
          <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre font-mono px-3 py-2 text-sm leading-6 text-foreground">
            {item.command}
          </code>
          <CopyButton text={item.command} label={`Copy the ${item.agent} install command`} compact />
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
  description: string;
}) {
  return (
    <div>
      <h2
        id={id}
        className="text-heading font-semibold tracking-tight text-foreground"
      >
        {title}
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {description}
      </p>
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

          <section id="get-started" aria-labelledby="get-started-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro
              id="get-started-title"
              title="Get Started"
              description="Copy this message to your agent. It finds the install for its app and sets it up."
            />
            <AgentMessage />
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

          <section id="installation" aria-labelledby="installation-title" className="scroll-mt-20 space-y-6 py-6">
            <SectionIntro
              id="installation-title"
              title="Install"
              description="Or install it yourself. The plugin brings the skills and CAD's viewer, a local server that runs through uv, which must be installed. Restart your agent if newly installed skills do not appear."
            />
            {installs.map((item) => (
              <Install key={item.agent} item={item} />
            ))}
          </section>
        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
