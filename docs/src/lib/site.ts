const DEFAULT_SITE_ORIGIN = "https://www.texttocad.dev";
const SITE_DESCRIPTION = "A library of agent skills for CAD, CAE and CAM";
const SITE_TITLE = `CAD Skills | ${SITE_DESCRIPTION}`;

function normalizeOrigin(value: string | undefined, fallback: string) {
  const candidate = value?.trim() || fallback;

  try {
    return new URL(candidate).origin;
  } catch {
    return fallback;
  }
}

export const siteConfig = {
  name: "CAD Skills",
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  keywords: [
    "CAD Skills",
    "text-to-cad",
    "CAD agents",
    "agent skills",
    "step.parts",
    "STEP parts",
    "DXF",
  ],
  origin: normalizeOrigin(process.env.NEXT_PUBLIC_SITE_URL, DEFAULT_SITE_ORIGIN),
};

export function absoluteUrl(path: string) {
  return new URL(path, `${siteConfig.origin}/`).toString();
}
