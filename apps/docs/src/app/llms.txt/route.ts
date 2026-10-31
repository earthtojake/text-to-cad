// /llms.txt: the homepage for an agent, as markdown (https://llmstxt.org). It says what the page
// says, from the same copy (src/lib/content.ts), so the two never drift apart.
import {
  contributing,
  howItWorks,
  installCommands,
  installSummary,
  manualInstall,
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
    "## How it works",
    "",
    ...howItWorks.map((step, index) => `${index + 1}. ${step}`),
    "",
    "## Install",
    "",
    ...installCommands.flatMap(({ system, language, command }) => [`${system}:`, "", "```" + language, command, "```", ""]),
    installSummary,
    "",
    `${manualInstall.label}: ${onGitHub(manualInstall.path)}`,
    "",
    "## Skills",
    "",
    ...skillGroups.map((skill) => `- [${skill.name}](${onGitHub(`${skill.path}/SKILL.md`)}): ${skill.summary}`),
    "",
    "## Contributing",
    "",
    contributing.intro,
    "",
    ...contributing.items.map(({ title, body, links }) =>
      `- **${title}**: ${body} ${links.map(({ text, href }) => `[${text}](${href})`).join(" ")}`
    ),
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
