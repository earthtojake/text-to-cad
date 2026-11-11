import { SiteHeaderClient } from "@/components/site-header-client";
import { getGitHubStars } from "@/lib/github";
import packageJson from "../../package.json";

/** The site's header: the C mark and "text-to-cad", linking home, then Docs, the version and GitHub
 * with its star count at the right. No theme toggle. `wide`: as wide as the documentation's columns. */
export async function SiteHeader({ wide = false }: { wide?: boolean }) {
  const githubStars = await getGitHubStars();
  return <SiteHeaderClient githubStars={githubStars} version={packageJson.version} wide={wide} />;
}
