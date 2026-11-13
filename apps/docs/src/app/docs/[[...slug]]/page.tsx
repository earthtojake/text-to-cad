import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Markdown } from "@/components/docs/markdown";
import { ModelEmbed } from "@/components/docs/model-embed";
import { DocsToc } from "@/components/docs/toc";
import { docModels, docPages, sectionOf } from "@/lib/docs/nav";
import { loadDoc, neighbours } from "@/lib/docs/source";
import { absoluteUrl, siteConfig } from "@/lib/site";

// Every page of the documentation is in the map (src/lib/docs/nav.ts) and built ahead: a path that
// is none of them is a 404, never rendered on request.
export const dynamicParams = false;

type Params = { slug?: string[] };
const slugOf = (params: Params) => (params.slug ?? []).join("/");

export function generateStaticParams(): Params[] {
  return docPages.map((page) => ({ slug: page.slug ? page.slug.split("/") : [] }));
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const doc = loadDoc(slugOf(await params));
  const title = doc.page.slug ? doc.title : "Documentation";
  return {
    title,
    description: doc.description,
    alternates: { canonical: doc.href, types: { "text/markdown": `${doc.href}.md` } },
    openGraph: { title: `${title} | ${siteConfig.name}`, description: doc.description, url: doc.href, type: "article" },
  };
}

export default async function DocsPage({ params }: { params: Promise<Params> }) {
  const slug = slugOf(await params);
  const doc = loadDoc(slug);
  const section = sectionOf(slug);
  const { previous, next } = neighbours(slug);
  const contents = doc.headings.filter((heading) => heading.depth === 2 || heading.depth === 3);
  // What search engines read: where the page sits in the documentation.
  const breadcrumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Documentation", item: absoluteUrl("/docs") },
      ...(slug ? [{ "@type": "ListItem", position: 2, name: doc.title, item: absoluteUrl(doc.href) }] : []),
    ],
  };

  return (
    <div className="flex">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbs).replace(/</g, "\\u003c") }} />
      <main className="min-w-0 flex-1 py-8 lg:px-10">
        <article className="mx-auto w-full max-w-[760px]">
          {section ? <p className="mb-2 text-sm font-medium text-brand">{section.title}</p> : null}
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{doc.title}</h1>
          {docModels[slug] ? <ModelEmbed {...docModels[slug]} /> : null}
          <Markdown doc={doc} />

          <footer className="mt-12 space-y-6 border-t border-border pt-6">
            <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
              <a
                href={`${siteConfig.repository}/blob/main/${doc.sourcePath}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 underline-offset-4 hover:text-foreground hover:underline"
              >
                This page on GitHub
                <ExternalLink className="size-3.5" aria-hidden="true" />
              </a>
              <a
                href={`${doc.href}.md`}
                className="underline-offset-4 hover:text-foreground hover:underline"
              >
                View as Markdown
              </a>
            </p>
            <nav aria-label="Next and previous pages" className="grid gap-3 sm:grid-cols-2">
              {previous ? (
                <Link
                  href={previous.href}
                  className="group/page rounded-xl border border-border px-4 py-3 outline-none transition-colors hover:bg-secondary/60 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <ArrowLeft className="size-3.5" aria-hidden="true" />
                    Previous
                  </span>
                  <span className="mt-0.5 block text-sm font-medium text-foreground">{previous.title}</span>
                </Link>
              ) : (
                <span />
              )}
              {next ? (
                <Link
                  href={next.href}
                  className="group/page rounded-xl border border-border px-4 py-3 text-right outline-none transition-colors hover:bg-secondary/60 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
                    Next
                    <ArrowRight className="size-3.5" aria-hidden="true" />
                  </span>
                  <span className="mt-0.5 block text-sm font-medium text-foreground">{next.title}</span>
                </Link>
              ) : null}
            </nav>
          </footer>
        </article>
      </main>
      <aside className="sticky top-14 hidden h-[calc(100svh-3.5rem)] w-56 shrink-0 overflow-y-auto py-8 pl-4 xl:block">
        <DocsToc headings={contents} />
      </aside>
    </div>
  );
}
