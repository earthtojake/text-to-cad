import { createHighlighter, type Highlighter } from "shiki";
import { CopyButton } from "@/components/copy-button";

/**
 * A fenced code block: highlighted as the site builds (Shiki, in the light and the dark theme at
 * once, each token's two colours as CSS variables that `.docs-code` in globals.css picks between),
 * with the site's Copy at its corner. No highlighting runs in the browser.
 */

const LANGUAGES = ["bash", "powershell", "python", "json", "toml", "yaml", "xml", "ini", "diff", "typescript", "tsx", "javascript"];
const ALIASES: Record<string, string> = { sh: "bash", shell: "bash", zsh: "bash", console: "bash", ps1: "powershell", py: "python", yml: "yaml", js: "javascript", ts: "typescript", gitignore: "ini" };

let highlighter: Promise<Highlighter> | undefined;
const shiki = () => (highlighter ??= createHighlighter({ themes: ["github-light", "github-dark"], langs: LANGUAGES }));

export async function CodeBlock({ language = "", code = "", copy = true }: { language?: string; code?: string; copy?: boolean }) {
  const name = ALIASES[language] ?? language;
  const html = (await shiki()).codeToHtml(code, {
    lang: LANGUAGES.includes(name) ? name : "text",
    themes: { light: "github-light", dark: "github-dark" },
    defaultColor: false,
  });
  return (
    <div className="docs-code group/code">
      <div dangerouslySetInnerHTML={{ __html: html }} />
      {copy ? (
        <CopyButton
          text={code}
          label="Copy code"
          className="absolute top-1.5 right-1.5 size-7 bg-background/70 text-muted-foreground backdrop-blur-sm hover:text-foreground md:opacity-0 md:group-hover/code:opacity-100 md:focus-visible:opacity-100"
        />
      ) : null}
    </div>
  );
}
