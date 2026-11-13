// /docs/<page>.md (next.config.ts rewrites it here): a page as Markdown, for an agent, with its links
// made absolute. /docs.md is /docs itself.
import { docPages } from "@/lib/docs/nav";
import { docMarkdown } from "@/lib/docs/source";

export const dynamic = "force-static";
export const dynamicParams = false;

type Params = { slug?: string[] };

export function generateStaticParams(): Params[] {
  return docPages.map((page) => ({ slug: page.slug ? page.slug.split("/") : [] }));
}

export async function GET(_request: Request, { params }: { params: Promise<Params> }) {
  const slug = ((await params).slug ?? []).join("/");
  return new Response(docMarkdown(slug), {
    headers: { "content-type": "text/markdown; charset=utf-8" },
  });
}
