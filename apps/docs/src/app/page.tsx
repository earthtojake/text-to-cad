import { ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/copy-button";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { absoluteUrl, siteConfig } from "@/lib/site";

const skillsInstallCommand = "npx skills add earthtojake/text-to-cad";

const pluginInstallCommands = [
  {
    agent: "Codex",
    command:
      "codex plugin marketplace add earthtojake/text-to-cad\ncodex plugin add text-to-cad@earthtojake",
  },
  {
    agent: "Claude Code",
    command:
      "claude plugin marketplace add earthtojake/text-to-cad\nclaude plugin install text-to-cad@earthtojake",
  },
  // Grok Build reads the same .claude-plugin/marketplace.json as Claude Code -- there is no
  // separate Grok manifest -- and installs straight from the repo rather than adding a
  // marketplace first, so it is one command, not two.
  {
    agent: "Grok Build",
    command: "grok plugin install earthtojake/text-to-cad --trust",
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

function InstallCommand({
  item,
}: {
  item: (typeof pluginInstallCommands)[number];
}) {
  return (
    <div className={COMMAND_BOX_CLASS}>
      <div className="border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
        {item.agent}
      </div>
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre font-mono px-3 py-2 text-sm leading-6 text-foreground">
          {item.command}
        </code>
        <CopyButton
          text={item.command}
          label={`Copy ${item.agent} install command`}
          prominent
          compact
        />
      </div>
    </div>
  );
}

function InstallCommands() {
  return (
    <div className="grid min-w-0 gap-2">
      {pluginInstallCommands.map((item) => (
        <InstallCommand key={item.agent} item={item} />
      ))}
    </div>
  );
}

function SkillsInstallCommand({ prominent = false }: { prominent?: boolean }) {
  return (
    <div className={COMMAND_BOX_CLASS}>
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre font-mono px-3 py-2 text-sm leading-6 text-foreground">
          {skillsInstallCommand}
        </code>
        <CopyButton
          text={skillsInstallCommand}
          label="Copy Skills CLI install command"
          prominent={prominent}
          compact
        />
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

          <section id="installation" aria-labelledby="installation-title" className="scroll-mt-20 py-6">
            <div className="w-full space-y-3">
              <h2 id="installation-title" className="text-heading font-semibold tracking-tight text-foreground">
                Install
              </h2>
              <SkillsInstallCommand prominent />
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

          <section
            id="plugins"
            aria-labelledby="plugins-title"
            className="scroll-mt-20 space-y-3 py-6"
          >
            <SectionIntro
              id="plugins-title"
              title="Plugins"
              description="Provider-native plugins are an alternative to installing with the Skills CLI."
            />
            <InstallCommands />
            <p className="text-sm leading-6 text-muted-foreground">
              Restart your agent if newly installed skills do not appear. The Codex
              plugin requires Codex 0.142.0 or newer; older versions skip it silently.
            </p>
          </section>
        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
