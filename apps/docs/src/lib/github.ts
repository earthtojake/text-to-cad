// The project's links outside the site, and its star count, shared by the header and the hero.

export const GITHUB_REPO_URL = "https://github.com/earthtojake/text-to-cad";

const GITHUB_REPO_API_URL = "https://api.github.com/repos/earthtojake/text-to-cad";
const DEFAULT_DISCORD_URL = "https://discord.gg/5FGB9DwJYU";

/** The Discord invite: `DISCORD_URL` when it is set and an http(s) address (a bare host gets
 * `https://`), the project's invite otherwise. */
export function normalizeDiscordUrl(value: string | undefined = process.env.DISCORD_URL) {
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

/** The repository's star count, or null when GitHub does not answer. Cached for an hour, so a build
 * fetches it once however many components ask. */
export async function getGitHubStars() {
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

export function formatGitHubStars(stars: number) {
  return new Intl.NumberFormat("en-US").format(stars);
}
