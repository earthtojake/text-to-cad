import { ExternalLink, LinkIcon } from "lucide-react";
import Image from "next/image";
import type { ReactNode } from "react";
import { FeatureGrid } from "@/components/feature-grid";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import {
  agents,
  contributing,
  howItWorks,
  pluginDescription,
  featuresIntro,
  pluginRequestUrl,
  support,
} from "@/lib/content";
import { absoluteUrl, siteConfig } from "@/lib/site";
import { withCode } from "@/lib/with-code";

// How a model is made, under the overview: the README's How it works.
function HowItWorks() {
  return (
    <div id="how-it-works" className="scroll-mt-20 space-y-1 pt-3">
      <h3 className="text-base font-semibold text-foreground">
        <TitleLink anchor="how-it-works">How it works</TitleLink>
      </h3>
      <ol className="list-decimal space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
        {howItWorks.map((step) => (
          <li key={step}>{withCode(step)}</li>
        ))}
      </ol>
    </div>
  );
}

// The agents' logos, scrolling as skills.sh's do: two copies side by side, moved one copy's width
// and over again, paused under the pointer, and still for anyone who asks for less motion. Each
// tile is a black square: it takes the page's own colour, lightened into the dark theme and, inverted,
// darkened into the light one. The track keeps the page's background behind it to blend with. The
// logos are not links: Install, below, covers them all.
function AgentCarousel() {
  const logos = (copy: number) => (
    <ul className={copy ? "flex shrink-0 motion-reduce:hidden" : "flex shrink-0"} aria-hidden={copy ? true : undefined}>
      {agents.map((agent) => (
        <li key={agent.logo} title={agent.name}>
          <Image
            src={`/agents/${agent.logo}.svg`}
            alt={agent.name}
            width={100}
            height={100}
            unoptimized
            className="h-[72px] w-auto invert mix-blend-darken lg:h-[88px] dark:invert-0 dark:mix-blend-lighten"
          />
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

// The ways to take part (`contributing`, the README's Contributing): each one's title, what it is,
// and its links, each opening in a new tab.
function Contributing() {
  return (
    <ul className="space-y-4">
      {contributing.items.map(({ title, body, links }) => (
        <li key={title} className="space-y-1">
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
          <p className="text-sm leading-6 text-muted-foreground">{withCode(body)}</p>
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {links.map(({ text, href }) => (
              <a
                key={text}
                href={href}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-foreground underline underline-offset-4"
              >
                {text}
                <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
              </a>
            ))}
          </p>
        </li>
      ))}
    </ul>
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
      image: absoluteUrl("/social-preview-products.png"),
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
      <SiteHeader />

      <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
        <div className="min-w-0 space-y-2">
          {/* Centred: the wordmark, the tagline, the two calls to action, the one-line install (the
              page's Install, `#install`), the framed CAD demo. */}
          <HeroSection />

          {/* Right under the hero's demo, a label over the agents' logos, no section title. */}
          <div id="agents" className="scroll-mt-20 space-y-3 py-6">
            <p className="text-center text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              WORKS WITH THESE AGENTS
            </p>
            <AgentCarousel />
            <p className="text-center text-sm leading-6 text-muted-foreground">
              No plugin for your agent yet?{" "}
              <a href={pluginRequestUrl} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
                Request one
              </a>
            </p>
          </div>

          <section id="overview" aria-labelledby="overview-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="overview" title="Overview" description={pluginDescription} />
            <p className="text-sm leading-6 text-muted-foreground">
              {support.before}{" "}
              <a href={support.link.href} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
                {support.link.text}
              </a>{" "}
              {support.after}
            </p>
            <HowItWorks />
          </section>

          <section id="features" aria-labelledby="features-title" className="scroll-mt-20 space-y-4 py-6">
            <SectionIntro section="features" title="Features" description={featuresIntro} />
            <FeatureGrid />
          </section>

          <section id="contributing" aria-labelledby="contributing-title" className="scroll-mt-20 space-y-3 py-6">
            <SectionIntro section="contributing" title="Contributing" description={contributing.intro} />
            <Contributing />
          </section>
        </div>
      </div>

      <SiteFooter />
    </main>
  );
}
