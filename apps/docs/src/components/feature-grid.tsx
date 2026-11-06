import { ExternalLink } from "lucide-react";
import type { CSSProperties } from "react";
import { FeatureArt } from "@/components/feature-art";
import { FeaturesReveal } from "@/components/features-reveal";
import { features } from "@/lib/content";
import { siteConfig } from "@/lib/site";

/**
 * The homepage's Features (`features`, the README's Features): one tile per feature, each a picture of
 * the file it makes over that file's name, framed as the hero's demo is, then its name, linking to the
 * page that documents it, and what it does. The grid gives the first two the widest tiles, then rows
 * of three and four; two columns on a tablet, one on a phone.
 */

// Each tile's place in the grid (12 columns wide, 2 on a tablet) and its picture's height.
const LAYOUT: Record<string, { tile: string; picture: string }> = {
  parts: { tile: "md:col-span-2 lg:col-span-7", picture: "h-auto md:h-60" },
  boards: { tile: "lg:col-span-5", picture: "h-48 lg:h-60" },
  checks: { tile: "lg:col-span-4", picture: "h-48" },
  drawings: { tile: "lg:col-span-4", picture: "h-48" },
  viewer: { tile: "lg:col-span-4", picture: "h-48" },
  cut: { tile: "lg:col-span-3", picture: "h-48" },
  sendcutsend: { tile: "lg:col-span-3", picture: "h-48" },
  print: { tile: "lg:col-span-3", picture: "h-48" },
  robots: { tile: "lg:col-span-3", picture: "h-48" },
};

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
    <div className="min-w-0 overflow-x-auto border-b border-border bg-muted/50 md:border-r md:border-b-0">
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
    <FeaturesReveal className="grid gap-4 md:grid-cols-2 lg:grid-cols-12">
      {features.map((feature, index) => {
        const layout = LAYOUT[feature.id] ?? { tile: "lg:col-span-4", picture: "h-48" };
        const picture = (
          <div
            className={`flex min-w-0 items-center justify-center px-3 py-4 bg-[radial-gradient(color-mix(in_oklch,var(--muted-foreground)_22%,transparent)_1px,transparent_1px)] [background-size:14px_14px] [background-position:7px_7px] ${feature.id === "parts" ? "h-52 md:h-full" : layout.picture}`}
          >
            <FeatureArt id={feature.id} />
          </div>
        );
        return (
          <li
            key={feature.id}
            data-feature={feature.id}
            style={{ "--feature-delay": `${(index % 3) * 90}ms` } as CSSProperties}
            className={`flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card ${layout.tile}`}
          >
            {feature.id === "parts" ? (
              <div className={`grid min-w-0 md:grid-cols-[auto_minmax(0,1fr)] md:grid-rows-1 ${layout.picture}`}>
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
              <p className="text-sm leading-6 text-muted-foreground">{feature.summary}</p>
            </div>
          </li>
        );
      })}
    </FeaturesReveal>
  );
}
