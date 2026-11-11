// /llms.txt: the homepage for an agent, as markdown (https://llmstxt.org). It says what the page
// says, from the same copy (src/lib/content.ts), so the two never drift apart, then lists the
// documentation's pages, each at its Markdown address (/docs/<page>.md).
import {
  contributing,
  features,
  featuresIntro,
  installCommands,
  installSummary,
  manualInstallPage,
  manualInstall,
  pluginDescription,
} from "@/lib/content";
import { navigation } from "@/lib/docs/source";
import { absoluteUrl, siteConfig } from "@/lib/site";

export const dynamic = "force-static";

const onGitHub = (path: string) => `${siteConfig.repository}/blob/main/${path}`;

export function GET() {
  const text = [
    `# ${siteConfig.name}`,
    "",
    `> ${pluginDescription}`,
    "",
    "## Install",
    "",
    ...installCommands.flatMap(({ system, language, command }) => [`${system}:`, "", "```" + language, command, "```", ""]),
    installSummary,
    "",
    `${manualInstall.label}: ${absoluteUrl(`${manualInstallPage}.md`)}`,
    "",
    "## Features",
    "",
    featuresIntro,
    "",
    ...features.map((feature) => `- [${feature.name}](${onGitHub(feature.path)}): ${feature.summary.replace(/\]\((skills\/[^)]+)\)/g, (_, path) => `](${onGitHub(path)})`)}`),
    "",
    // The documentation: every page, as Markdown (`/docs/<page>.md`).
    ...navigation().flatMap((section) => [
      `## Docs: ${section.title}`,
      "",
      ...section.pages.map((page) => `- [${page.label}](${absoluteUrl(`${page.href}.md`)})`),
      "",
    ]),
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
