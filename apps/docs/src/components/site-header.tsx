import { SiteHeaderClient } from "@/components/site-header-client";
import packageJson from "../../package.json";

const GITHUB_REPO_API_URL =
  "https://api.github.com/repos/earthtojake/text-to-cad";
const DEFAULT_DISCORD_URL = "https://discord.gg/5FGB9DwJYU";

function normalizeDiscordUrl(value: string | undefined) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return DEFAULT_DISCORD_URL;
  }

  const urlValue = /^[a-z][a-z\d+.-]*:\/\//i.test(rawValue)
    ? rawValue
    : `https://${rawValue.replace(/^\/+/, "")}`;

  try {
    const url = new URL(urlValue);
    return ["http:", "https:"].includes(url.protocol)
      ? url.href
      : DEFAULT_DISCORD_URL;
  } catch {
    return DEFAULT_DISCORD_URL;
  }
}

async function getGitHubStars() {
  try {
    const response = await fetch(GITHUB_REPO_API_URL, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "cad-skills-docs",
      },
      next: { revalidate: 60 * 60 },
    });

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as { stargazers_count?: unknown };
    const stars = Number(data.stargazers_count);

    return Number.isFinite(stars) ? stars : null;
  } catch {
    return null;
  }
}

/** `heroWordmark`: the page shows the hero's wordmark (`#hero-wordmark`), and the navbar shows the CAD
 * logo only once it is out of sight; without one, the logo is always there. */
export async function SiteHeader({ heroWordmark = false }: { heroWordmark?: boolean }) {
  const githubStars = await getGitHubStars();
  return (
    <SiteHeaderClient
      heroWordmark={heroWordmark}
      githubStars={githubStars}
      discordUrl={normalizeDiscordUrl(process.env.DISCORD_URL)}
      version={packageJson.version}
    />
  );
}
