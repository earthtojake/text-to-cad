// /llms.txt: the homepage for an agent, as markdown (https://llmstxt.org). It says what the page
// says, from the same copy (src/lib/content.ts), so the two never drift apart.
import {
  agentInstallByline,
  agentInstallMessage,
  installs,
  pluginDescription,
  skillGroups,
  support,
} from "@/lib/content";
import { absoluteUrl, siteConfig } from "@/lib/site";

export const dynamic = "force-static";

const onGitHub = (path: string) => `${siteConfig.repository}/blob/main/${path}`;

export function GET() {
  const text = [
    `# ${siteConfig.name}`,
    "",
    `> ${pluginDescription}`,
    "",
    `${support.before} [${support.link.text}](${support.link.href}) ${support.after}`,
    "",
    "## Install",
    "",
    agentInstallByline,
    "",
    "```text",
    agentInstallMessage,
    "```",
    "",
    ...installs.flatMap((item) => [
      `### ${item.agent}`,
      "",
      ...(item.note ? [item.note, ""] : []),
      "```bash",
      item.command,
      "```",
      "",
    ]),
    `The README has each install's full notes: ${siteConfig.repository}#readme`,
    "",
    "## Skills",
    "",
    ...skillGroups.map((skill) => `- [${skill.name}](${onGitHub(`${skill.path}/SKILL.md`)}): ${skill.summary}`),
    "",
    "## Optional",
    "",
    `- [Repository](${siteConfig.repository})`,
    `- [Contributing](${onGitHub("CONTRIBUTING.md")})`,
    `- [Privacy policy](${absoluteUrl("/privacy-policy")})`,
    `- [Terms of service](${absoluteUrl("/terms-of-service")})`,
    "",
  ].join("\n");
  return new Response(text, { headers: { "content-type": "text/plain; charset=utf-8" } });
}
