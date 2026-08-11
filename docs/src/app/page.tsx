import { ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/copy-button";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

const skillsInstallCommand = "npx skills install earthtojake/text-to-cad";

const pluginInstallCommands = [
  {
    agent: "Codex",
    command:
      "codex plugin marketplace add earthtojake/text-to-cad\ncodex plugin add cad@text-to-cad",
  },
  {
    agent: "Claude Code",
    command:
      "claude plugin marketplace add earthtojake/text-to-cad\nclaude plugin install cad@text-to-cad",
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
    name: "CAD Viewer",
    path: "skills/cad-viewer",
    summary: "Shows local browser previews for CAD and robot files.",
  },
  {
    name: "step.parts",
    path: "skills/step-parts",
    summary:
      "Finds off-the-shelf STEP parts like screws, bearings, motors, and connectors.",
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
    name: "G-code",
    path: "skills/gcode",
    summary:
      "Slices supported mesh files into validated, printer-profiled FDM .gcode with real slicer CLIs.",
  },
  {
    name: "Bambu Labs",
    path: "skills/bambu-labs",
    summary:
      "Dry-runs, uploads, and cautiously starts local Bambu Lab print jobs from validated .gcode.",
  },
  {
    name: "Implicit CAD",
    path: "skills/implicit-cad",
    summary:
      "Creates browser-native implicit CAD models using GLSL signed-distance fields and CAD Viewer raymarch rendering. Experimental.",
  },
];

function InstallCommand({
  item,
}: {
  item: (typeof pluginInstallCommands)[number];
}) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden border border-border bg-card">
      <div className="border-b border-border px-3 py-2 text-label uppercase tracking-[1.5px] text-muted-foreground">
        {item.agent}
      </div>
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre px-3 py-2 text-sm leading-6 text-foreground">
          {item.command}
        </code>
        <CopyButton
          text={item.command}
          label={`Copy ${item.agent} install command`}
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

function SkillsInstallCommand() {
  return (
    <div className="min-w-0 max-w-full overflow-hidden border border-border bg-card">
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre px-3 py-2 text-sm leading-6 text-foreground">
          {skillsInstallCommand}
        </code>
        <CopyButton
          text={skillsInstallCommand}
          label="Copy Skills CLI install command"
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
        className="text-heading font-medium tracking-normal text-foreground"
      >
        {title}
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

function SkillLink({ skill }: { skill: (typeof skillGroups)[number] }) {
  return (
    <a
      className="inline-flex min-w-0 items-center gap-1.5 text-label uppercase tracking-[1.5px] text-primary transition hover:text-primary/80"
      href={`https://github.com/earthtojake/text-to-cad/blob/main/${skill.path}/SKILL.md`}
      target="_blank"
      rel="noreferrer"
    >
      <span className="truncate">{skill.path}</span>
      <ExternalLink className="size-3 shrink-0" />
    </a>
  );
}

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6">
        <div className="min-w-0 space-y-2">
          <HeroSection />

          <section aria-label="Install text-to-cad" className="py-6">
            <div className="max-w-3xl space-y-3">
              <h2 className="text-sm font-medium uppercase tracking-[1.5px] text-foreground">
                Try It Now
              </h2>
              <SkillsInstallCommand />
            </div>
          </section>

          <section
            id="skills"
            aria-labelledby="skills-title"
            className="scroll-mt-20 space-y-3 py-6"
          >
            <SectionIntro
              id="skills-title"
              title="SKILLS"
              description="Install the library to give agents focused workflows for CAD, fabrication, robot description files, simulation, and local review."
            />

            <div className="border border-border bg-card">
              <div className="grid grid-cols-[minmax(0,1fr)] border-b border-border px-3.5 py-2.5 text-xs uppercase tracking-[1.5px] text-muted-foreground md:grid-cols-[minmax(9rem,12rem)_minmax(0,1fr)_max-content] md:gap-5 md:pl-0 md:pr-3.5">
                <span className="md:pl-3.5">skill</span>
                <span className="hidden md:block">summary</span>
                <span className="hidden text-right md:block">source</span>
              </div>
              <ul className="divide-y divide-border">
                {skillGroups.map((skill) => (
                  <li
                    key={skill.name}
                    className="card-glow grid gap-3 px-3.5 py-3 hover:bg-secondary/60 md:grid-cols-[minmax(9rem,12rem)_minmax(0,1fr)_max-content] md:items-center md:gap-5 md:pl-0 md:pr-3.5"
                  >
                    <div className="flex min-w-0 items-center md:pl-3.5">
                      <div className="min-w-0">
                        <h3 className="text-sm font-medium text-foreground">
                          {skill.name}
                        </h3>
                        <p className="mt-0.5 text-label uppercase tracking-wider text-muted-foreground md:hidden">
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
            id="installation"
            aria-labelledby="installation-title"
            className="scroll-mt-20 space-y-3 py-6"
          >
            <SectionIntro
              id="installation-title"
              title="INSTALL"
              description="Install CAD Skills with the Skills CLI. Provider-native plugin installs are available as a secondary path."
            />

            <div className="max-w-3xl space-y-3">
              <SkillsInstallCommand />
              <div className="pt-3">
                <h3 className="mb-3 text-sm font-medium uppercase tracking-[1.5px] text-foreground">
                  Plugin Installs
                </h3>
                <InstallCommands />
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                Skills CLI installation is preferred for regular use. Restart
                your agent if newly installed skills do not appear. The Codex
                plugin install requires Codex 0.142.0 or newer; older versions
                skip the plugin silently.
              </p>
              <p className="text-sm leading-6 text-muted-foreground">
                Local development symlink guidance lives in{" "}
                <a
                  className="inline-flex items-center gap-1 text-primary transition hover:text-primary/80"
                  href="https://github.com/earthtojake/text-to-cad/blob/main/CONTRIBUTING.md"
                  rel="noreferrer"
                  target="_blank"
                >
                  CONTRIBUTING.md
                  <ExternalLink className="size-3" aria-hidden="true" />
                </a>
                .
              </p>
            </div>
          </section>
        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
