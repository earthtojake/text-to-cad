/**
 * The documentation's map: every page under /docs, the section it sits in, and where its text
 * comes from. A page is either a file of this app's (`content/`, written for the site) or a file of
 * the repository's (`docs/`), rendered as it is: the repository's file stays the one copy. The build
 * fails on a page whose file is missing.
 */

export type DocSource =
  // A page written for the site: `apps/docs/content/<file>`.
  | { kind: "content"; file: string }
  // A file of the repository, by its path from the repository's root.
  | { kind: "repo"; file: string }
  // A page made as the site builds from a generated file of the repository's (`reference/`): the
  // command line's help or the library's docstrings, by its path from the repository's root.
  | { kind: "generated"; page: "cli" | "library"; file: string };

export type DocPage = {
  /** The path under /docs: "" is /docs itself, "render" is /docs/render. */
  slug: string;
  source: DocSource;
  /** The name in the sidebar, where it is not the page's title. */
  label?: string;
};

/** A model a page shows live, under its title (`ModelEmbed`): a GLB of `public/`, a plain file. */
export type DocModel = { src: string; label: string; caption: string; clip?: string; clipSpeed?: number };

// The planetary gear the homepage's hero draws (apps/docs/README.md): the one model the site holds.
const planetary: DocModel = {
  src: "/hero/planetary.glb",
  label: "A planetary gear set turning: a sun gear, three planets on a carrier and a ring gear.",
  caption:
    "A planetary gear set, modelled as a Python script and exported with cad model export as one GLB: its parts, their colours and the motion of its joints, baked into a clip. Drag to turn it.",
  clip: "meshCycle",
  clipSpeed: 0.25,
};

export const docModels: Record<string, DocModel> = {
  cad: planetary,
};

export type DocSection = { title: string; pages: DocPage[] };

const content = (slug: string, label?: string): DocPage => ({
  slug,
  source: { kind: "content", file: `${slug || "index"}.md` },
  label,
});
const index = (slug: string, label = "Overview"): DocPage => ({
  slug,
  source: { kind: "content", file: `${slug}/index.md` },
  label,
});
const repo = (slug: string, file: string, label?: string): DocPage => ({ slug, source: { kind: "repo", file }, label });
const generated = (slug: string, page: "cli" | "library", label: string): DocPage => ({
  slug,
  source: { kind: "generated", page, file: `apps/docs/src/lib/docs/${page}-reference.generated.json` },
  label,
});
// A skill's page: /docs/<skill>, written in `content/skills/<skill>.md`, its title the skill's name.
const skill = (name: string): DocPage => ({ slug: name, source: { kind: "content", file: `skills/${name}.md` } });

export const docSections: DocSection[] = [
  {
    title: "Get started",
    pages: [
      { slug: "", source: { kind: "content", file: "index.md" }, label: "Introduction" },
      repo("install", "docs/install.md", "Install"),
      content("first-model"),
      content("viewer"),
      content("agents"),
    ],
  },
  {
    // One page per skill (the folders of skills/), named after it: what the skill is, what it makes,
    // how it works and where it stops. The homepage's feature tiles (`features` in
    // src/lib/content.ts) link these pages.
    title: "Skills",
    pages: ["cad", "pcb", "fea", "engineering-drawing", "render", "print3d", "sendcutsend", "robot-simulation"].map(skill),
  },
  {
    // Generated from the command line's and the library's own descriptions of themselves
    // (src/lib/docs/reference/): every command and every public name, nothing written by hand.
    title: "Reference",
    pages: [generated("reference/cli", "cli", "The cad command"), generated("reference/library", "library", "The cad library")],
  },
  {
    title: "Migrations",
    pages: [
      index("migrations"),
      repo("migrations/0.10-to-0.11", "docs/migrations/migrating-0.10-to-0.11.md", "0.10 to 0.11"),
      repo("migrations/0.8-to-0.10", "docs/migrations/migrating-0.8-to-0.10.md", "0.8 to 0.10"),
      repo("migrations/0.7-to-0.8", "docs/migrations/migrating-0.7-to-0.8.md", "0.7 to 0.8"),
      repo("migrations/0.4-to-0.5", "docs/migrations/migrating-0.4-to-0.5.md", "0.4 to 0.5"),
      repo("migrations/opencascade-8", "docs/migrations/migrating-to-opencascade-8.md", "OpenCASCADE 8"),
    ],
  },
  {
    // The contributing guides (docs/contributing) are written for whoever changes the repository,
    // an agent as often as a person: the Contributing page links them on GitHub, and the site does
    // not set them.
    title: "Contributing",
    pages: [index("contributing")],
  },
];

export const docPages: DocPage[] = docSections.flatMap((section) => section.pages);

export const docHref = (slug: string) => (slug ? `/docs/${slug}` : "/docs");

export function findPage(slug: string) {
  return docPages.find((page) => page.slug === slug);
}

export function sectionOf(slug: string) {
  return docSections.find((section) => section.pages.some((page) => page.slug === slug));
}
