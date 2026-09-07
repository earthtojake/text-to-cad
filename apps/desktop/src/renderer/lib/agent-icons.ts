/**
 * The agents' own marks, from the public ACP registry.
 *
 * `scripts/fetch-agent-icons.mjs` downloads them into
 * `src/renderer/assets/agents/<providerId>.svg` and they are committed; the
 * `icon` column in `src/main/agents/registry.ts` names the one a provider uses.
 * Kiro's comes from kiro.dev and Hermes's is a hand-wrapped raster favicon
 * (see the fetch script); the rest are the registry's.
 *
 * Every one of them is drawn in `currentColor`, which is why they are inlined
 * as markup rather than loaded through `<img>`: an external SVG has no
 * inherited colour, so a mark that is black on white in light mode would be
 * black on black in dark. Inline, they are the colour of the text beside them
 * and both themes come out right with no per-icon work.
 */

// Raw markup, not URLs, for the reason above. Eager: twenty-one small files
// that every Agents page render needs.
const SOURCES = import.meta.glob("../assets/agents/*.svg", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

/**
 * The vendors' files carry `width="16" height="16"`, which would win over the
 * size the container asks for. They are replaced with 100% — an attribute
 * rather than a class, because the markup goes in through
 * `dangerouslySetInnerHTML` and Tailwind never sees it to emit a utility for.
 * One regular expression here beats a hand-edit in twenty-one committed files
 * that the fetch script would undo.
 */
function scalable(svg: string): string {
  return svg.replace(/^<svg\b[^>]*>/, (tag) =>
    tag
      .replace(/\s(?:width|height)="[^"]*"/g, "")
      .replace("<svg", '<svg width="100%" height="100%"'),
  );
}

const BY_ID: Record<string, string> = Object.fromEntries(
  Object.entries(SOURCES).map(([file, svg]) => [
    file.split("/").pop()!.replace(/\.svg$/, ""),
    scalable(svg),
  ]),
);

/**
 * The markup for an agent's mark, or null when there is none — `AgentMark`
 * draws a letter in that case rather than a hole.
 *
 * Exported as a helper rather than a component so P2's composer chip can use
 * the same assets without importing anything from Settings.
 */
export function agentIcon(icon: string | null | undefined): string | null {
  return (icon && BY_ID[icon]) ?? null;
}

/** Every provider id an icon was downloaded for. Used by the tests. */
export function agentIconIds(): string[] {
  return Object.keys(BY_ID).sort();
}
