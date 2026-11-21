/**
 * /docs/reference/library, "The cad library": the library's own description of its public names
 * (`library-reference.generated.json`, `python -m cad._internal.reference --docs`) set as one Markdown
 * page, as the command line's page is (`cli.ts`). Each name is a heading whose id is its dotted path
 * (`#cad.step.export`) and whose kind shows beside it (`{#id kind=...}`, read by `source.ts`), then
 * its signature, and its docstring made Markdown (`text.ts`).
 */
import generated from "../library-reference.generated.json";
import { commandId } from "./cli";
import { blocks, codeSpan, inline, table } from "./text";

type Kind =
  | "decorator"
  | "function"
  | "class"
  | "attribute"
  | "object"
  | "module"
  | "property"
  | "method"
  | "classmethod"
  | "staticmethod";
export type Member = {
  name: string;
  kind: Kind;
  signature?: string;
  summary?: string;
  operation?: boolean;
  doc?: number;
  bases?: string[];
  type?: string;
  value?: string;
  module?: string;
  members?: Member[];
};
type Namespace = { name: string; module: string; title?: string; doc?: number; members?: Member[] };
type LibraryReference = { module: string; doc?: number; names: Member[]; documentTypes: Namespace[]; integrations: Namespace[]; texts: string[] };

export const library = generated as unknown as LibraryReference;

const doc = (index: number | undefined) => (index === undefined ? "" : (library.texts[index] ?? ""));

// A module's docstring opens with its own name (``cad.step``: the STEP document type...), which its
// heading already says: the page starts at what follows, its first letter a capital.
function moduleDoc(index: number | undefined, module: string) {
  const whole = doc(index);
  const text = whole.replace(new RegExp(`^(\`\`)?${module.replace(/\./g, "\\.")}\\1:\\s*`), "");
  return text === whole ? text : text.charAt(0).toUpperCase() + text.slice(1);
}
const prose = { dashes: true } as const;

/** A heading with the id and the kind `source.ts` reads off its end. */
const heading = (level: number, label: string, id: string, kind?: string) =>
  `${"#".repeat(level)} ${codeSpan(label)} {#${id}${kind ? ` kind=${kind}` : ""}}`;

// The bracket that closes the one opening at `start`, past strings and nested brackets.
function closing(text: string, start: number) {
  let depth = 0;
  let quote = "";
  for (let at = start; at < text.length; at += 1) {
    const char = text[at];
    if (quote) {
      if (char === "\\") at += 1;
      else if (char === quote) quote = "";
    } else if (char === "'" || char === '"') quote = char;
    else if ("([{".includes(char)) depth += 1;
    else if (")]}".includes(char) && --depth === 0) return at;
  }
  return -1;
}

// The parameters of `(a: int, b: dict[str, int] = {}) -> R`, split at their own commas.
function parameters(inner: string) {
  const out: string[] = [];
  let depth = 0;
  let quote = "";
  let current = "";
  for (let at = 0; at < inner.length; at += 1) {
    const char = inner[at];
    if (quote) {
      if (char === "\\") current += inner[(at += 1) - 1];
      else if (char === quote) quote = "";
    } else if (char === "'" || char === '"') quote = char;
    else if ("([{".includes(char)) depth += 1;
    else if (")]}".includes(char)) depth -= 1;
    else if (char === "," && depth === 0) {
      out.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  if (current.trim()) out.push(current.trim());
  return out;
}

const WIDTH = 88;

/** A callable's signature as Python would print it, a parameter a line where one line is too long. */
export function formatSignature(prefix: string, signature: string) {
  const one = `${prefix}${signature}`;
  if (one.length <= WIDTH || !signature.startsWith("(")) return one;
  const end = closing(signature, 0);
  if (end < 0) return one;
  const params = parameters(signature.slice(1, end));
  if (params.length < 2) return one;
  return `${prefix}(\n${params.map((param) => `    ${param},`).join("\n")}\n)${signature.slice(end + 1)}`;
}

function signatureOf(member: Member, path: string) {
  switch (member.kind) {
    case "decorator":
      return member.signature ? formatSignature(`@${path}`, member.signature) : `@${path}`;
    case "class":
      return member.signature
        ? formatSignature(`class ${path}`, member.signature)
        : `class ${path}${member.bases?.length ? `(${member.bases.join(", ")})` : ""}`;
    case "attribute":
    case "property":
      return `${path}${member.type ? `: ${member.type}` : ""}${member.value !== undefined ? ` = ${member.value}` : ""}`;
    case "function":
    case "method":
    case "classmethod":
    case "staticmethod":
      return formatSignature(path, member.signature ?? "()");
    default:
      return member.signature ? formatSignature(path, member.signature) : "";
  }
}

// A type's decorator is the object itself (`@cad.step(...)`), so its id is its own.
const memberId = (member: Member, parent: string) =>
  member.kind === "decorator" && parent.endsWith(`.${member.name}`) ? `${parent}.decorator` : `${parent}.${member.name}`;
const memberLabel = (member: Member, parent: string) =>
  member.kind === "decorator" && parent.endsWith(`.${member.name}`) ? `@${parent}` : `${parent}.${member.name}`;

function memberMarkdown(member: Member, parent: string, level: number, out: string[], commands: Set<string>) {
  const id = memberId(member, parent);
  const path = member.kind === "decorator" && parent.endsWith(`.${member.name}`) ? parent : `${parent}.${member.name}`;
  out.push(heading(level, memberLabel(member, parent), id, member.kind));
  const signature = signatureOf(member, path);
  if (signature) out.push("```python nocopy\n" + signature + "\n```");
  if (member.kind === "class" && member.signature && member.bases?.length) {
    out.push(`Bases: ${member.bases.map((base) => codeSpan(base)).join(", ")}.`);
  }
  if (member.operation) {
    // One to one with a command: `cad.step.export` is `cad step export`.
    const command = path.replace(/\./g, " ");
    const summary = member.summary ? `: ${inline(member.summary, { flags: true })}` : "";
    out.push(
      commands.has(command)
        ? `The command [${codeSpan(command)}](/docs/reference/cli#${commandId(command)})${summary}.`.replace(/\.\.$/, ".")
        : member.summary
          ? inline(member.summary, prose)
          : "",
    );
  } else if (member.summary) {
    out.push(inline(member.summary, prose));
  }
  if (member.doc !== undefined) out.push(blocks(doc(member.doc), prose));
  for (const child of member.members ?? []) memberMarkdown(child, path, Math.min(level + 1, 6), out, commands);
}

const memberIds = (members: Member[] | undefined, parent: string): string[] =>
  (members ?? []).flatMap((member) => {
    const path = member.kind === "decorator" && parent.endsWith(`.${member.name}`) ? parent : `${parent}.${member.name}`;
    return [memberId(member, parent), ...memberIds(member.members, path)];
  });

/** Every anchor the library page has: what the command line's page may link. */
export function libraryIds() {
  return new Set([
    library.module,
    ...memberIds(library.names, library.module),
    ...[...library.documentTypes, ...library.integrations].flatMap((space) => [space.module, ...memberIds(space.members, space.module)]),
  ]);
}

/** The page: its title, what it is, and its Markdown. `commands` are the command line's commands. */
export function libraryPage(version: string, commands: Set<string>) {
  const out: string[] = [
    "`cad` is the Python library a model is written with: `import cad`, then the document types, their decorators and their operations, and the integrations' helpers. A model's script runs with `cad run`, which puts this release of the library and the integrations the script imports on its path, so a script names no installation of its own.",
    `A program of your own that imports \`cad\` names the release exactly, \`cad==${version}\` (with an integration's extra, \`cad[build123d]==${version}\`): PyPI's \`cad\` project holds unrelated earlier releases an open requirement would pick. \`cad requirement\` prints the exact requirement for this release.`,
  ];

  out.push(heading(2, library.module, library.module, "module"));
  if (library.doc !== undefined) out.push(blocks(moduleDoc(library.doc, library.module), prose));
  for (const member of library.names) memberMarkdown(member, library.module, 3, out, commands);

  out.push(
    "## Document types",
    "One object a type, each its decorator where it has one, its reader, its edit, and its operations, one to one with the `cad <type> <operation>` commands.",
    table(
      ["Object", "Type", "Members"],
      library.documentTypes.map((type) => [
        `[${codeSpan(type.module, true)}](#${type.module})`,
        inline(type.title ?? type.name, { table: true }),
        (type.members ?? [])
          .map((member) => `[${codeSpan(member.kind === "decorator" ? `@${type.name}` : member.name, true)}](#${memberId(member, type.module)})`)
          .join(", "),
      ]),
    ),
  );
  for (const type of library.documentTypes) {
    out.push(heading(3, type.module, type.module, "object"));
    if (type.doc !== undefined) out.push(blocks(moduleDoc(type.doc, type.module), prose));
    for (const member of type.members ?? []) memberMarkdown(member, type.module, 4, out, commands);
  }

  out.push(
    "## Integrations",
    "An integration's module holds the helpers that take or answer its tool's own objects. Each loads on first use, and a script whose environment lacks the tool is told which extra brings it.",
  );
  for (const integration of library.integrations) {
    out.push(heading(3, integration.module, integration.module, "module"));
    if (integration.doc !== undefined) out.push(blocks(moduleDoc(integration.doc, integration.module), prose));
    for (const member of integration.members ?? []) memberMarkdown(member, integration.module, 4, out, commands);
  }

  return {
    title: "The cad library (Python)",
    description:
      "Every public name of the cad Python library, generated from its docstrings: the root module, each document type's object and each integration's module.",
    markdown: out.join("\n\n") + "\n",
  };
}
