import { ChevronRight, ExternalLink, LinkIcon } from "lucide-react";
import Image from "next/image";
import type { ReactNode } from "react";
import { agentLogos } from "@/components/agent-logos";
import { CopyButton } from "@/components/copy-button";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  agentInstallByline,
  agentInstallLinks,
  agentInstallMessage,
  agents,
  installs,
  pluginDescription,
  pluginRequestUrl,
  skillGroups,
  support,
} from "@/lib/content";
import { absoluteUrl, siteConfig } from "@/lib/site";

const COMMAND_BOX_CLASS =
  "min-w-0 w-full overflow-hidden rounded-lg border border-border bg-card shadow-xs";

function AgentMessage() {
  return (
    <div className={COMMAND_BOX_CLASS}>
      <div className="flex min-h-[54px] min-w-0 max-w-full flex-col items-stretch sm:flex-row">
        <p className="flex min-w-0 flex-1 items-center break-words px-3 pt-2 font-mono text-sm leading-6 text-foreground sm:py-2">
          {agentInstallMessage}
        </p>
        <div className="flex shrink-0 items-center justify-end gap-1.5 p-2">
          {agentInstallLinks.map(({ id, agent, href }) => {
            const Logo = agentLogos[id];
            return (
              <Tooltip key={id}>
                <TooltipTrigger asChild>
                  <Button asChild variant="secondary" size="icon-lg">
                    <a href={href} aria-label={`Open in ${agent}`}>
                      <Logo className="size-4" />
                    </a>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Open in {agent}</TooltipContent>
              </Tooltip>
            );
          })}
          <CopyButton text={agentInstallMessage} label="Copy the message for your agent" />
        </div>
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

function Command({ text, label }: { text: string; label: string }) {
  return (
    <div className={COMMAND_BOX_CLASS}>
      <div className="flex min-h-[54px] min-w-0 max-w-full items-stretch">
        <code className="flex min-w-0 flex-1 items-center overflow-x-auto whitespace-pre font-mono px-3 py-2 text-sm leading-6 text-foreground">
          {text}
        </code>
        <CopyButton text={text} label={label} className="m-2 self-center" />
      </div>
    </div>
  );
}

// A fold, closed until opened: how to update and reinstall an install, or an app's commands where
// it leads with its own plugin directory.
function Fold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-sm leading-6 text-muted-foreground transition hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
        {label}
      </summary>
      <div className="mt-2 space-y-2">{children}</div>
    </details>
  );
}

// A title that links to its own section, as GitHub's headings do: following it puts the section in the
// address bar, to share or come back to. Its icon shows on hover and focus.
function TitleLink({ anchor, children }: { anchor: string; children: ReactNode }) {
  return (
    <a href={`#${anchor}`} className="group/title inline-flex items-center gap-2 rounded-sm">
      {children}
      <LinkIcon
        className="size-[0.7em] shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover/title:opacity-100 group-focus-visible/title:opacity-100"
        aria-hidden="true"
      />
    </a>
  );
}

// An install, and under it, folded away, how to update it and how to reinstall it: where the CAD
// app's update button sends a person who updates by hand (/install). An app listed in its own plugin
// directory leads with a button to the listing, its commands folded under Manual install.
function Install({ item }: { item: (typeof installs)[number] }) {
  const Logo = agentLogos[item.id];
  const updateOrReinstall = (
    <>
      {item.update ? (
        <>
          <p className="text-sm leading-6 text-muted-foreground">Update, then restart the app:</p>
          <Command text={item.update} label={`Copy the ${item.agent} update command`} />
        </>
      ) : (
        <p className="text-sm leading-6 text-muted-foreground">Run the install command again to update or reinstall, then restart the app.</p>
      )}
      {item.remove ? (
        <>
          <p className="text-sm leading-6 text-muted-foreground">Reinstall: remove it, then install it again:</p>
          <Command text={item.remove} label={`Copy the ${item.agent} remove command`} />
        </>
      ) : null}
    </>
  );
  return (
    <div id={item.id} className="min-w-0 scroll-mt-20 space-y-2">
      <div>
        <h3 className="text-base font-semibold text-foreground">
          <TitleLink anchor={item.id}>{item.agent}</TitleLink>
        </h3>
        {item.note ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.note}</p> : null}
      </div>
      {item.listing ? (
        <>
          <Button asChild className="h-11 gap-2 px-5 text-base">
            <a href={item.listing.href} target="_blank" rel="noreferrer">
              {Logo ? <Logo className="size-5" /> : null}
              {item.listing.label}
            </a>
          </Button>
          <Fold label="Manual install">
            <Command text={item.command} label={`Copy the ${item.agent} install command`} />
            {updateOrReinstall}
          </Fold>
        </>
      ) : (
        <>
          <Command text={item.command} label={`Copy the ${item.agent} install command`} />
          <Fold label="Update or reinstall">{updateOrReinstall}</Fold>
        </>
      )}
    </div>
  );
}

// A section's title, `<section>-title` (the section's label), linking to the section.
function SectionIntro({
  section,
  title,
  description,
}: {
  section: string;
  title: string;
  description?: string;
}) {
  return (
    <div>
      <h2
        id={`${section}-title`}
        className="text-heading font-semibold tracking-tight text-foreground"
      >
        <TitleLink anchor={section}>{title}</TitleLink>
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

          {/* Right under the hero, so a phone shows the agents on load. */}
          <section id="agents" aria-labelledby="agents-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="agents" title="Available for these agents" />
            <AgentCarousel />
          </section>

          <section id="overview" aria-labelledby="overview-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="overview" title="Overview" description={pluginDescription} />
            <p className="text-sm leading-6 text-muted-foreground">
              {support.before}{" "}
              <a href={support.link.href} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
                {support.link.text}
              </a>{" "}
              {support.after}
            </p>
          </section>

          <section id="install" aria-labelledby="install-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="install" title="Install" />
            <div id="ask-your-agent" className="scroll-mt-20 space-y-3">
              <div>
                <h3 className="text-base font-semibold text-foreground">
                  <TitleLink anchor="ask-your-agent">Ask your agent (recommended)</TitleLink>
                </h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{agentInstallByline}</p>
              </div>
              <AgentMessage />
            </div>
            <div className="space-y-6 pt-6">
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
              section="skills"
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


          <section id="contributing" aria-labelledby="contributing-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="contributing" title="Contributing" />
            <p className="text-sm leading-6 text-muted-foreground">
              Branch from <code className="font-mono text-foreground">main</code> and open PRs against{" "}
              <code className="font-mono text-foreground">main</code>. For the local workflow, testing in agent apps
              and validation, see{" "}
              <a href={`${siteConfig.repository}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noreferrer"
                className="text-foreground underline underline-offset-4">
                CONTRIBUTING.md
              </a>
              .
            </p>
          </section>
        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
