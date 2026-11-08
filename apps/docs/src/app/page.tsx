import { ExternalLink, LinkIcon } from "lucide-react";
import type { ReactNode } from "react";
import { FeatureGrid } from "@/components/feature-grid";
import { HeroSection } from "@/components/hero-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { contributing, featuresIntro } from "@/lib/content";
import { absoluteUrl, siteConfig } from "@/lib/site";
import { withCode } from "@/lib/with-code";

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

      {/* The first screen: the wordmark, the tagline, the two calls to action and the one-line
          install (the page's Install, `#install`) over the turning gear, then the agents. */}
      <HeroSection />

      <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
        <div className="min-w-0 space-y-2">
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
