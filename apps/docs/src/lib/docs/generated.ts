/**
 * The sections a page gets from the registry, under its written text: which pages have them, the
 * headings they add (so the page's contents list and its anchors know them), and the same facts as
 * Markdown, for /docs/<page>.md.
 */
import { documentType, integration, registry, usesOf, viewSummaries } from "./registry";

type GeneratedHeading = { depth: number; id: string; text: string };

export type GeneratedKind =
  | { kind: "document-types" }
  | { kind: "document-type"; id: string }
  | { kind: "integrations" }
  | { kind: "integration"; name: string }
  | { kind: "operations" };

export function generatedKind(slug: string): GeneratedKind | null {
  if (slug === "document-types") return { kind: "document-types" };
  if (slug === "integrations") return { kind: "integrations" };
  if (slug === "reference/commands") return { kind: "operations" };
  const [section, name, ...rest] = slug.split("/");
  if (rest.length || !name) return null;
  if (section === "document-types" && documentType(name)) return { kind: "document-type", id: name };
  if (section === "integrations" && integration(name)) return { kind: "integration", name };
  return null;
}

export function generatedHeadings(slug: string): GeneratedHeading[] {
  const generated = generatedKind(slug);
  const h2 = (id: string, text: string) => ({ depth: 2, id, text });
  switch (generated?.kind) {
    case "document-types":
      return [h2("all-document-types", "All document types")];
    case "integrations":
      return [h2("all-integrations", "All integrations")];
    case "document-type":
      return [h2("facts", "Facts"), h2("operations", "Operations"), h2("what-writes-it", "What writes it")];
    case "integration": {
      const entry = integration(generated.name)!;
      return [
        h2("facts", "Facts"),
        ...(entry.operations.length ? [h2("operations", "Operations")] : []),
        ...(usesOf(entry.name).length ? [h2("where-it-is-used", "Where it is used")] : []),
      ];
    }
    default:
      return [];
  }
}

/** A type's command for an operation: a model is named by its document id, every other type by a file. */
export function operationCommand(typeId: string, operation: string) {
  return `cad ${typeId} ${operation} ${typeId === "model" ? "<id>" : "<file>"}`;
}

/** What writes a type's files, in the registry's words (`cad.registry.help_text`). */
export function writers(typeId: string): string[] {
  const entry = documentType(typeId)!;
  const suffix = entry.extensions[0] ?? "";
  if (entry.edit) {
    return [
      `\`with ${entry.id}.edit("${entry.edit.noun}${suffix}") as ${entry.edit.noun}:\` ${entry.edit.hands}, changed in place and saved at the block's end when changed (${entry.edit.integration}: ${entry.edit.changes.join(", ")}).`,
    ];
  }
  if (!entry.producers.length) return ["No producer: a file of it is authored."];
  return entry.producers.map((producer) =>
    entry.extensions.length
      ? `\`@${entry.id}("out${suffix}")\` of ${producer.accepts} (${producer.integration}: ${producer.provides.join(", ")}).`
      : `\`@${entry.id}\` on a function returning ${producer.accepts.replace(/ a model returns$/, "")} (${producer.integration}: ${producer.provides.join(", ")}).`,
  );
}

const row = (cells: string[]) => `| ${cells.join(" | ")} |`;
const table = (head: string[], rows: string[][]) =>
  [row(head), row(head.map(() => "---")), ...rows.map(row)].join("\n");

/** A page's generated sections as Markdown. */
export function generatedMarkdown(slug: string): string {
  const generated = generatedKind(slug);
  switch (generated?.kind) {
    case "document-types":
      return [
        "## All document types",
        "",
        table(
          ["Type", "Id", "Files", "Viewed as", "Operations"],
          registry.documentTypes.map((entry) => [
            entry.title,
            `\`${entry.id}\``,
            entry.extensions.map((extension) => `\`${extension}\``).join(" ") || "none (held by the engine)",
            entry.view,
            entry.operations.map((operation) => `\`${operation.name}\``).join(" "),
          ]),
        ),
      ].join("\n");
    case "integrations":
      return [
        "## All integrations",
        "",
        table(
          ["Integration", "Extra", "What it brings", "Download"],
          registry.integrations.map((entry) => [
            `\`${entry.name}\``,
            entry.extra ? `\`cad[${entry.extra}]\`` : "none",
            entry.holds,
            `about ${entry.downloadMb} MB`,
          ]),
        ),
      ].join("\n");
    case "document-type": {
      const entry = documentType(generated.id)!;
      return [
        "## Facts",
        "",
        `- Id: \`${entry.id}\``,
        `- What it is: ${entry.summary}`,
        `- Files: ${entry.extensions.map((extension) => `\`${extension}\``).join(", ") || "none (a model is held by the engine)"}`,
        ...(entry.mime ? [`- MIME type: \`${entry.mime}\``] : []),
        `- Viewed as: ${entry.view}, ${viewSummaries[entry.view]}`,
        `- Carries: ${entry.content.join(", ")}`,
        "",
        "## Operations",
        "",
        table(
          ["Operation", "Command", "What it does", "Needs"],
          entry.operations.map((operation) => [
            `\`${operation.name}\``,
            `\`${operationCommand(entry.id, operation.name)}\``,
            operation.summary.replace(/\|/g, "\\|"),
            operation.integration ?? "",
          ]),
        ),
        "",
        "## What writes it",
        "",
        ...writers(entry.id).map((line) => `- ${line}`),
      ].join("\n");
    }
    case "integration": {
      const entry = integration(generated.name)!;
      const uses = usesOf(entry.name);
      return [
        "## Facts",
        "",
        `- Name: \`${entry.name}\``,
        `- What it is: ${entry.summary}`,
        `- Extra: ${entry.extra ? `\`cad[${entry.extra}]\`` : "none"}`,
        `- Brings: ${entry.holds}, about ${entry.downloadMb} MB to download`,
        `- Runs: ${entry.process}`,
        ...(entry.platforms.length ? [`- Platforms: ${entry.platforms.join(", ")}`] : []),
        ...(entry.python ? [`- Python: ${entry.python}`] : []),
        ...(entry.commands.length ? [`- Commands: ${entry.commands.map((command) => `\`cad run ${command}\``).join(", ")}`] : []),
        ...(entry.operations.length
          ? [
              "",
              "## Operations",
              "",
              ...entry.operations.map(
                (operation) => `- \`cad ${entry.name} ${operation.name} <file>\` (${entry.files.join(", ")}): ${operation.summary}`,
              ),
            ]
          : []),
        ...(uses.length
          ? ["", "## Where it is used", "", ...uses.map(({ type, uses: names }) => `- ${type.title} (\`${type.id}\`): ${names.join(", ")}`)]
          : []),
      ].join("\n");
    }
    case "operations":
      return table(
        ["Type", ...registry.operations.map((name) => `\`${name}\``)],
        registry.documentTypes.map((entry) => [
          `\`${entry.id}\``,
          ...registry.operations.map((name) => (entry.operations.some((operation) => operation.name === name) ? "yes" : "")),
        ]),
      );
    default:
      return "";
  }
}
