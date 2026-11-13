/**
 * Text of the generated reference pages, made Markdown: the command line's help (argparse) and the
 * library's docstrings, which are reStructuredText-ish. Not an RST parser: ``code``, :role:`target`
 * and `code` become code spans, **strong** stays strong, `::` literal blocks and indented blocks
 * become Python, `* ` and `- ` lines become lists and `name: text` lines a list of fields. Everything
 * else is escaped, so a help text's `<uri>`, `[x0, y0]` or `|` is shown as written.
 */

export type InlineOptions = {
  /** Inside a table cell: a `|`, even in code, is escaped, and nothing breaks the line. */
  table?: boolean;
  /** Command-line help: a `--flag` written in the text is set as code. */
  flags?: boolean;
  /** A docstring: ` -- ` is a dash. */
  dashes?: boolean;
};

export function codeSpan(content: string, table = false) {
  const text = (table ? content.replace(/\|/g, "\\|") : content).replace(/\s*\n\s*/g, " ");
  const longest = Math.max(0, ...(text.match(/`+/g) ?? []).map((run) => run.length));
  const fence = "`".repeat(longest + 1);
  const pad = text.startsWith("`") || text.endsWith("`") ? " " : "";
  return `${fence}${pad}${text}${pad}${fence}`;
}

// Escapes what Markdown would read as markup in prose: HTML, emphasis, a link's `](`, a table's pipe,
// strikethrough, an entity and an e-mail autolink (`walk@0.6`).
function escapeProse(text: string, options: InlineOptions) {
  let out = text
    .replace(/[\\`*<>|~]/g, "\\$&")
    .replace(/(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])/g, "\\_")
    .replace(/\](?=[([])/g, "\\]")
    .replace(/&(?=#?[A-Za-z0-9]+;)/g, "\\&")
    .replace(/(?<=\w)@(?=\w)/g, "\\@");
  if (options.dashes) out = out.replace(/ -- /g, " — ");
  return out;
}

const INLINE = /``(.+?)``|:[a-z]+:`([^`]+)`|`([^`\n]+)`|\*\*([^*\n]+?)\*\*/g;
const FLAG = /(?<![\w-])--[a-z][a-z0-9-]*/g;

function prose(text: string, options: InlineOptions) {
  if (!options.flags) return escapeProse(text, options);
  let out = "";
  let at = 0;
  for (const match of text.matchAll(FLAG)) {
    out += escapeProse(text.slice(at, match.index), options) + codeSpan(match[0], options.table);
    at = match.index + match[0].length;
  }
  return out + escapeProse(text.slice(at), options);
}

/** One line of text, its markup made Markdown and the rest escaped. */
export function inline(text: string, options: InlineOptions = {}) {
  const flat = text.replace(/\s*\n\s*/g, " ").trim();
  let out = "";
  let at = 0;
  for (const match of flat.matchAll(INLINE)) {
    out += prose(flat.slice(at, match.index), options);
    const [, double, role, single, strong] = match;
    if (strong !== undefined) out += `**${prose(strong, options)}**`;
    else if (role !== undefined) {
      // :class:`~cad.results.CheckResult` shows its last name, as Sphinx does.
      const target = role.startsWith("~") ? role.slice(1).split(".").at(-1)! : role;
      out += codeSpan(target, options.table);
    } else out += codeSpan(double ?? single, options.table);
    at = match.index + match[0].length;
  }
  return out + prose(flat.slice(at), options);
}

/** A help text as a sentence: its first letter capital, a full stop at its end. */
export function sentence(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  const capital = /^[a-z][a-z]*(?=[\s,:;(]|$)/.test(trimmed) ? trimmed[0].toUpperCase() + trimmed.slice(1) : trimmed;
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

// A paragraph that would open as a block of Markdown (a heading, a list, a quote) is kept a paragraph.
function guardStart(markdown: string) {
  return markdown.replace(/^(#{1,6}\s|[-+]\s|\d+[.)]\s|=+\s*$)/, (start) =>
    /^\d/.test(start) ? start.replace(/([.)])/, "\\$1") : `\\${start}`,
  );
}

const indentOf = (line: string) => line.length - line.trimStart().length;
const FIELD = /^([A-Za-z_]\w*):\s+(.*)$/;
const BULLET = /^[*-]\s+(.*)$/;

/** A docstring (or a long help text) as Markdown blocks: paragraphs, lists, fields and code. */
export function blocks(text: string, options: InlineOptions = {}) {
  const groups: string[][] = [[]];
  for (const line of text.replace(/\r/g, "").replace(/\t/g, "    ").split("\n")) {
    if (line.trim()) groups.at(-1)!.push(line.trimEnd());
    else if (groups.at(-1)!.length) groups.push([]);
  }
  const out: string[] = [];
  let literalNext = false;
  let code: string[] | null = null;
  const closeCode = () => {
    if (!code) return;
    const indent = Math.min(...code.filter((line) => line.trim()).map(indentOf));
    const body = code.map((line) => line.slice(indent)).join("\n").replace(/\n+$/, "");
    const fence = "`".repeat(Math.max(3, ...(body.match(/`{3,}/g) ?? []).map((run) => run.length + 1)));
    out.push(`${fence}python\n${body}\n${fence}`);
    code = null;
  };

  for (const group of groups.filter((lines) => lines.length)) {
    const indented = group.every((line) => indentOf(line) >= (literalNext ? 2 : 4));
    if (indented || (code && group.every((line) => indentOf(line) >= 2))) {
      code = code ? [...code, "", ...group] : [...group];
      literalNext = false;
      continue;
    }
    closeCode();
    literalNext = /::$/.test(group.at(-1)!);
    const lines = group.map((line, index) =>
      index === group.length - 1 ? line.replace(/\s*::$/, (end) => (/\s/.test(end[0]) ? "" : ":")) : line,
    );

    // Items: a line that opens one, then the lines indented under it.
    const items = (opens: RegExp) => {
      const list: string[] = [];
      for (const line of lines) {
        if (opens.test(line.trimStart()) && indentOf(line) <= indentOf(lines[0])) list.push(line.trim());
        else if (list.length) list[list.length - 1] += ` ${line.trim()}`;
        else return null;
      }
      return list;
    };
    const base = indentOf(lines[0]);
    const opensOnly = (opens: RegExp) =>
      lines.every((line) => (indentOf(line) === base ? opens.test(line.trimStart()) : indentOf(line) > base));

    if (BULLET.test(lines[0].trimStart())) {
      const list = items(BULLET);
      if (list) {
        out.push(list.map((item) => `- ${guardStart(inline(BULLET.exec(item)![1], options))}`).join("\n"));
        continue;
      }
    }
    if (opensOnly(FIELD)) {
      const list = items(FIELD)!;
      out.push(
        list
          .map((item) => {
            const [, name, rest] = FIELD.exec(item)!;
            return `- ${codeSpan(name)}: ${inline(rest, options)}`;
          })
          .join("\n"),
      );
      continue;
    }
    out.push(guardStart(inline(lines.join("\n"), options)));
  }
  closeCode();
  return out.join("\n\n");
}

/** A table: its header and its rows, each cell already Markdown for a table. */
export function table(header: string[], rows: string[][], align?: ("left" | "center")[]) {
  const rule = header.map((_, index) => (align?.[index] === "center" ? ":---:" : "---"));
  return [header, rule, ...rows].map((cells) => `| ${cells.map((cell) => cell || " ").join(" | ")} |`).join("\n");
}
