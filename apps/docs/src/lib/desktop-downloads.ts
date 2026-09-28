// `RELEASE_API_URL` overrides the lookup for a preview or a local run that wants to
// show installers before a release carries them (a static JSON in GitHub's shape).
const LATEST_RELEASE_API_URL =
  process.env.RELEASE_API_URL ||
  "https://api.github.com/repos/earthtojake/text-to-cad/releases/latest";
export const RELEASES_URL = "https://github.com/earthtojake/text-to-cad/releases";

/**
 * The desktop app's installers, from the latest GitHub Release.
 *
 * The release workflow attaches one installer per platform beside the Python
 * distributions, named `text-to-cad-<version>-<os>-<arch>.<ext>` by
 * electron-builder (`apps/desktop/electron-builder.yml`). The names carry the
 * version, so the site cannot link a fixed URL; it asks the API for the latest
 * release and picks each platform's file by its suffix. Fetched on the server
 * with a one-hour revalidation, like the header's star count; the site is
 * redeployed by every release as well, so a new version shows within the hour
 * at worst. A release with no installers (every desktop leg failed, or a
 * release cut before the app shipped) yields an empty list, and the section
 * says so rather than showing dead buttons.
 */
export type DesktopInstaller = {
  /** Stable id for keys and tests. */
  id: "mac-arm64" | "mac-x64" | "win-x64" | "linux-appimage" | "linux-deb";
  platform: string;
  detail: string;
  url: string;
  fileName: string;
  /** Bytes, as GitHub reports them. */
  size: number;
};

export type DesktopDownloads = {
  version: string | null;
  releaseUrl: string;
  installers: DesktopInstaller[];
};

const PLATFORMS: ReadonlyArray<{
  id: DesktopInstaller["id"];
  platform: string;
  detail: string;
  matches: (name: string) => boolean;
}> = [
  { id: "mac-arm64", platform: "macOS", detail: "Apple silicon · .dmg", matches: (n) => /-mac-arm64\.dmg$/.test(n) },
  { id: "mac-x64", platform: "macOS", detail: "Intel · .dmg", matches: (n) => /-mac-x64\.dmg$/.test(n) },
  { id: "win-x64", platform: "Windows", detail: "x64 · installer", matches: (n) => /-win-x64-setup\.exe$/.test(n) },
  { id: "linux-appimage", platform: "Linux", detail: "x64 · AppImage", matches: (n) => /-linux-x64\.AppImage$/.test(n) },
  { id: "linux-deb", platform: "Linux", detail: "x64 · .deb", matches: (n) => /-linux-x64\.deb$/.test(n) },
];

type ReleaseAsset = { name?: unknown; browser_download_url?: unknown; size?: unknown };
type Release = { tag_name?: unknown; html_url?: unknown; assets?: unknown };

/** Pure: the installers a release's asset list offers, in platform order. Exported for the test. */
export function pickInstallers(assets: readonly ReleaseAsset[]): DesktopInstaller[] {
  const installers: DesktopInstaller[] = [];
  for (const platform of PLATFORMS) {
    const asset = assets.find((candidate) => typeof candidate.name === "string" && platform.matches(candidate.name));
    if (!asset || typeof asset.browser_download_url !== "string") continue;
    installers.push({
      id: platform.id,
      platform: platform.platform,
      detail: platform.detail,
      url: asset.browser_download_url,
      fileName: String(asset.name),
      size: Number.isFinite(Number(asset.size)) ? Number(asset.size) : 0,
    });
  }
  return installers;
}

export async function getDesktopDownloads(): Promise<DesktopDownloads> {
  const none: DesktopDownloads = { version: null, releaseUrl: RELEASES_URL, installers: [] };
  try {
    const response = await fetch(LATEST_RELEASE_API_URL, {
      headers: { Accept: "application/vnd.github+json", "User-Agent": "text-to-cad-docs" },
      next: { revalidate: 60 * 60 },
    });
    if (!response.ok) return none;
    const release = (await response.json()) as Release;
    const version = typeof release.tag_name === "string" ? release.tag_name.replace(/^v/, "") : null;
    const releaseUrl = typeof release.html_url === "string" ? release.html_url : RELEASES_URL;
    const assets = Array.isArray(release.assets) ? (release.assets as ReleaseAsset[]) : [];
    return { version, releaseUrl, installers: pickInstallers(assets) };
  } catch {
    return none;
  }
}

/** "456 MB", the way a download button says it. */
export function formatSize(bytes: number): string {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1000 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}
