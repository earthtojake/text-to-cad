import { SiteHeaderClient } from "@/components/site-header-client";
import { getGitHubStars } from "@/lib/github";
import packageJson from "../../package.json";

/** The site's header: the C mark and "text-to-cad", linking home, then the version and GitHub with
 * its star count at the right. No section links, no theme toggle. */
export async function SiteHeader() {
  const githubStars = await getGitHubStars();
  return <SiteHeaderClient githubStars={githubStars} version={packageJson.version} />;
}
