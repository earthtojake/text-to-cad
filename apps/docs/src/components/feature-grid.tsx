import { ExternalLink } from "lucide-react";
import type { CSSProperties } from "react";
import { FeatureArt } from "@/components/feature-art";
import { FeaturesReveal } from "@/components/features-reveal";
import { features } from "@/lib/content";
import { siteConfig } from "@/lib/site";

/**
 * The homepage's Features (`features`, the README's Features): one tile per feature, each a picture of
 * the file it makes over that file's name in a caption bar, then its name, linking to the
 * page that documents it, and what it does (its summary's links are markdown, as the README's are).
 * Two columns from a tablet up, one on a phone.
 */

// Each tile's picture height. Six tiles in two columns from a tablet up, one on a phone.
const PICTURE = "h-48 lg:h-60";

// A summary's links, written as markdown (`[text](href)`, as the README says them): a path in the
// repository links to its page on GitHub.
function Summary({ text }: { text: string }) {
  return text.split(/(\[[^\]]+\]\([^)]+\))/).map((part, index) => {
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (!link) return part;
    const href = link[2].startsWith("http") ? link[2] : `${siteConfig.repository}/blob/main/${link[2]}`;
    return (
      <a key={index} href={href} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
        {link[1]}
      </a>
    );
  });
}

// The script the Parts tile shows beside its bracket: a model as the cad skill writes one, which
// builds the bracket every other bracket drawing shows.
const BRACKET_SCRIPT = [
  "import build123d as bd",
  "from cad import model",
  "",
  "@model",
  "def bracket():",
  "    plate = bd.Box(60, 40, 4)",
  "    wall = bd.Pos(0, -18, 22) * bd.Box(60, 4, 40)",
  "    hole = bd.Pos(0, 6) * bd.Cylinder(4, 10)",
  "    return plate + wall - hole",
];

// Python, lightly: keywords and the decorator in the brand blue, numbers in the foreground.
function highlight(line: string) {
  return line.split(/(\b(?:import|from|as|def|return)\b|@model|\b\d+\b)/).map((part, index) => {
    if (!part) return null;
    if (/^(import|from|as|def|return|@model)$/.test(part)) return <span key={index} className="text-brand">{part}</span>;
    if (/^\d+$/.test(part)) return <span key={index} className="text-foreground">{part}</span>;
    return part;
  });
}

function BracketScript() {
  return (
    <div className="min-w-0 overflow-x-auto border-b border-border bg-muted/50 md:hidden lg:block lg:border-r lg:border-b-0">
      <pre className="px-4 py-3.5 font-mono text-[11px] leading-[1.7] text-muted-foreground">
        <code>
          {BRACKET_SCRIPT.map((line, index) => (
            <span key={index} className="block min-h-[1.7em]">
              {highlight(line)}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

export function FeatureGrid() {
  return (
    <FeaturesReveal className="grid gap-4 md:grid-cols-2">
      {features.map((feature, index) => {
        const picture = (
          <div
            className={`flex min-w-0 items-center justify-center px-3 py-4 bg-[radial-gradient(color-mix(in_oklch,var(--muted-foreground)_22%,transparent)_1px,transparent_1px)] [background-size:14px_14px] [background-position:7px_7px] ${feature.id === "parts" ? "h-52 md:h-48 lg:h-full" : PICTURE}`}
          >
            <FeatureArt id={feature.id} />
          </div>
        );
        return (
          <li
            key={feature.id}
            data-feature={feature.id}
            style={{ "--feature-delay": `${(index % 3) * 90}ms` } as CSSProperties}
            className={`flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card`}
          >
            {feature.id === "parts" ? (
              <div className="grid min-w-0 lg:h-60 lg:grid-cols-[auto_minmax(0,1fr)] lg:grid-rows-1">
                <BracketScript />
                {picture}
              </div>
            ) : (
              picture
            )}
            <p className="flex min-h-8 shrink-0 items-center border-y border-border px-3 py-[7px] font-mono text-label leading-none text-muted-foreground">
              <span className="min-w-0 truncate">{feature.file}</span>
            </p>
            <div className="flex-1 space-y-1 px-4 pt-3 pb-4">
              <h3 className="text-sm font-medium text-foreground">
                <a
                  href={`${siteConfig.repository}/blob/main/${feature.path}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-sm underline-offset-4 hover:underline"
                >
                  {feature.name}
                  <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                </a>
              </h3>
              <p className="text-sm leading-6 text-muted-foreground"><Summary text={feature.summary} /></p>
            </div>
          </li>
        );
      })}
    </FeaturesReveal>
  );
}
