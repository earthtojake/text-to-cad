const DEFAULT_SITE_ORIGIN = "https://www.texttocad.dev";
// The tagline the GitHub repository is found by, as the title's second half and the description's first
// sentence; then what the project is and does, inside the ~160 characters a search result shows.
const SITE_TAGLINE = "Give your agent CAD superpowers.";
const SITE_TITLE = `text-to-cad | ${SITE_TAGLINE.replace(/\.$/, "")}`;
const SITE_DESCRIPTION = `${SITE_TAGLINE} Free, open-source CAD for AI agents like Codex and Claude Code: generate STEP, STL and 3MF models, check DFM, make drawings.`;

function normalizeOrigin(value: string | undefined, fallback: string) {
  const candidate = value?.trim() || fallback;

  try {
    return new URL(candidate).origin;
  } catch {
    return fallback;
  }
}

export const siteConfig = {
  name: "text-to-cad",
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  // The repository's topics, and what people search for to find it.
  keywords: [
    "text-to-cad",
    "text to CAD",
    "AI CAD",
    "CAD agent",
    "AI agents",
    "agent skills",
    "Codex",
    "Claude Code",
    "build123d",
    "STEP",
    "STL",
    "3MF",
    "GLB",
    "DXF",
    "URDF",
    "3D printing",
    "CNC machining",
    "design for manufacturing",
    "engineering drawings",
    "mechanical engineering",
    "robotics",
  ],
  repository: "https://github.com/earthtojake/text-to-cad",
  author: { name: "earthtojake", url: "https://x.com/earthtojake", handle: "@earthtojake" },
  origin: normalizeOrigin(process.env.NEXT_PUBLIC_SITE_URL, DEFAULT_SITE_ORIGIN),
};

export function absoluteUrl(path: string) {
  return new URL(path, `${siteConfig.origin}/`).toString();
}
