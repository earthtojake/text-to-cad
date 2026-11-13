import { SiteHeaderClient } from "@/components/site-header-client";
import { getGitHubStars } from "@/lib/github";

/** The site's header: the C mark and "text-to-cad", linking home, then Docs and GitHub with its star
 * count at the right. No theme toggle. `wide`: as wide as the documentation's columns. */
export async function SiteHeader({ wide = false }: { wide?: boolean }) {
  const githubStars = await getGitHubStars();
  return <SiteHeaderClient githubStars={githubStars} wide={wide} />;
}
