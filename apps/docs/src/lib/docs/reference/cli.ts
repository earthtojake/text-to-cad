/**
 * /docs/reference/cli, "The cad command": the command line's own description of itself
 * (`cli-reference.generated.json`, `python -m cad_server._internal.cli_reference --docs`) set as one
 * Markdown page, so the table of contents, the page's Markdown, the search and /llms.txt read it as
 * they read any page. Nothing here is written by hand but the introduction and the groups below:
 * every command the JSON has is on the page, a command no group names under "Other".
 */
import generated from "../cli-reference.generated.json";
import { registry } from "../registry";
import { blocks, codeSpan, inline, sentence, table } from "./text";

type Argument = { name: string; help?: number; choices?: string[]; optional?: boolean; repeatable?: boolean };
type Option = {
  flags: string[];
  metavar?: string;
  help?: number;
  choices?: string[];
  default?: string | number | boolean | null;
  required?: boolean;
  repeatable?: boolean;
};
export type CliCommand = {
  command: string;
  summary: string;
  usage: string;
  description?: number;
  epilog?: string | number;
  arguments?: Argument[];
  options?: Option[];
};
type CliGroup = { name: string; summary: string; usage: string; operations: CliCommand[] };
type CliReference = { usage: string; documentTypes: CliGroup[]; integrations: CliGroup[]; commands: CliCommand[]; texts: string[] };

export const cli = generated as unknown as CliReference;

// The plain commands, by what a person does with them, in the order each group lists them.
const GROUPS: { title: string; intro: string; commands: string[] }[] = [
  {
    title: "Set-up and updates",
    intro:
      "Commands that remove things ask first, with a `(y/N)` in a terminal, or take `--yes`. `--only` limits `cad setup`, `cad update` and `cad uninstall` to the apps you name. [Installing by hand](/docs/install) says what each does to each app.",
    commands: ["cad setup", "cad update", "cad update auto", "cad uninstall", "cad doctor", "cad plugin", "cad telemetry"],
  },
  {
    title: "The server",
    intro: "One server runs for your installation: the first command starts it, and every command and the viewer go through it.",
    commands: ["cad status", "cad stop", "cad server", "cad serve"],
  },
  {
    title: "Running and viewing",
    intro: "",
    commands: ["cad run", "cad viewer", "cad delete", "cad requirement"],
  },
];

const text = (index: number | string | undefined) =>
  index === undefined ? "" : typeof index === "number" ? (cli.texts[index] ?? "") : index;

const help = { flags: true, dashes: true } as const;
const cell = { flags: true, dashes: true, table: true } as const;

/** The heading id GitHub gives `cad step export`: what a link to a command names. */
export const commandId = (command: string) => command.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s/g, "-");

function argumentsTable(args: Argument[]) {
  return table(
    ["Argument", "Description"],
    args.map((arg) => {
      const notes = [
        text(arg.help) ? sentence(inline(text(arg.help), cell)) : "",
        arg.choices?.length ? `One of ${arg.choices.map((choice) => codeSpan(choice, true)).join(", ")}.` : "",
        arg.optional ? "Optional." : "",
        arg.repeatable ? "Repeatable." : "",
      ];
      return [codeSpan(arg.name, true), notes.filter(Boolean).join(" ") || "—"];
    }),
  );
}

function optionsTable(options: Option[]) {
  const defaults = options.some((option) => option.default !== undefined && option.default !== null);
  // A metavar that only spells the choices (`{a,b,c}`) says nothing the description does not.
  const metavar = (option: Option) => (option.metavar && !option.metavar.startsWith("{") ? ` ${option.metavar}` : "");
  return table(
    defaults ? ["Option", "Description", "Default"] : ["Option", "Description"],
    options.map((option) => {
      const notes = [
        option.required ? "**Required.**" : "",
        text(option.help) ? sentence(inline(text(option.help), cell)) : "",
        option.choices?.length ? `One of ${option.choices.map((choice) => codeSpan(choice, true)).join(", ")}.` : "",
        option.repeatable ? "Repeatable." : "",
      ];
      const row = [
        option.flags.map((flag, index) => codeSpan(index === option.flags.length - 1 ? `${flag}${metavar(option)}` : flag, true)).join(", "),
        notes.filter(Boolean).join(" ") || "—",
      ];
      if (defaults) row.push(option.default === undefined || option.default === null ? "" : codeSpan(String(option.default), true));
      return row;
    }),
  );
}

function command(cmd: CliCommand, level: number, library?: string) {
  // Its description where it has one (the summary is its group's table's), else its summary.
  const parts = [
    `${"#".repeat(level)} ${codeSpan(cmd.command)}`,
    cmd.description !== undefined ? blocks(text(cmd.description), help) : sentence(inline(cmd.summary, help)),
    "```text nocopy\n" + cmd.usage + "\n```",
  ];
  if (cmd.epilog !== undefined) parts.push(blocks(text(cmd.epilog), help));
  if (library) parts.push(`In Python: [${codeSpan(library)}](/docs/reference/library#${library}).`);
  if (cmd.arguments?.length) parts.push(argumentsTable(cmd.arguments));
  if (cmd.options?.length) parts.push(optionsTable(cmd.options));
  return parts.join("\n\n");
}

/** The page: its title, what it is, and its Markdown. `libraryIds` are the library page's anchors. */
export function cliPage(libraryIds: Set<string>) {
  const libraryOf = (cmd: CliCommand) => {
    const id = cmd.command.replace(/^cad /, "cad.").replace(/ /g, ".");
    return libraryIds.has(id) ? id : undefined;
  };
  const out: string[] = [
    "`cad` is the command your agent runs, and you can run it yourself. The install command writes it at `~/.local/bin/cad` (on Windows, `%USERPROFILE%\\.local\\bin\\cad.exe`); it runs the one text-to-cad server on your computer, which keeps its workers warm between calls.",
    "`cad --help` lists every command, `cad <type> --help` a document type's operations, and `cad <command> --help` a command's options. This page is that help, generated from the same parser.",
    "```text nocopy\n" + cli.usage.split(" | ").join("\n") + "\n```",
  ];

  // The matrix: each document type's operations, each a link to its command below.
  const operations = registry.operations.filter((op) =>
    cli.documentTypes.some((type) => type.operations.some((cmd) => cmd.command === `cad ${type.name} ${op}`)),
  );
  out.push(
    "## Operations by document type",
    "A document type is a kind of file text-to-cad builds, shows or checks. Each has the operations that make sense for it, with one pattern: `cad <document_type> <operation> <file>`. A `model` is a model the server holds, named by its id; every other type takes a file.",
    table(
      ["Type", ...operations.map((op) => codeSpan(op, true))],
      cli.documentTypes.map((type) => [
        `[${codeSpan(type.name, true)}](#${commandId(`cad ${type.name}`)})`,
        ...operations.map((op) => {
          const cmd = `cad ${type.name} ${op}`;
          return type.operations.some((each) => each.command === cmd) ? `[✓](#${commandId(cmd)})` : "";
        }),
      ]),
      ["left", ...operations.map(() => "center" as const)],
    ),
  );

  const placed = new Set(GROUPS.flatMap((group) => group.commands));
  const groups = [
    ...GROUPS.map((group) => ({ ...group, cmds: group.commands.flatMap((name) => cli.commands.filter((cmd) => cmd.command === name)) })),
    { title: "Other", intro: "", cmds: cli.commands.filter((cmd) => !placed.has(cmd.command)) },
  ];
  for (const group of groups.filter((each) => each.cmds.length)) {
    out.push(`## ${group.title}`);
    if (group.intro) out.push(group.intro);
    out.push(
      table(
        ["Command", "Description"],
        group.cmds.map((cmd) => [`[${codeSpan(cmd.command, true)}](#${commandId(cmd.command)})`, sentence(inline(cmd.summary, cell))]),
      ),
    );
    for (const cmd of group.cmds) out.push(command(cmd, 3));
  }

  const kinds: [string, string, CliGroup[]][] = [
    ["Document types", "Each type's operations, as `cad <document_type> <operation>`. A file of another type is refused by name, and a check prints its findings, or with `--json` one JSON document.", cli.documentTypes],
    ["Integrations", "An integration is a tool text-to-cad runs for you. For a file of its tool's own that is no document type, it has operations of its own, as `cad <integration> <operation>`.", cli.integrations],
  ];
  for (const [title, intro, list] of kinds) {
    if (!list.length) continue;
    out.push(`## ${title}`, intro);
    for (const group of list) {
      const known = registry.documentTypes.find((type) => type.id === group.name);
      const integration = registry.integrations.find((each) => each.name === group.name);
      out.push(`### ${codeSpan(`cad ${group.name}`)}`);
      if (known) {
        out.push(
          `${known.title}: ${inline(sentence(known.summary), help)}` +
            (known.extensions.length ? ` Files: ${known.extensions.map((ext) => codeSpan(ext)).join(", ")}.` : ""),
        );
      } else {
        out.push(sentence(inline(integration?.summary ?? group.summary, help)));
      }
      out.push("```text nocopy\n" + group.usage + "\n```");
      const library = libraryIds.has(`cad.${group.name}`) ? `cad.${group.name}` : undefined;
      if (library) out.push(`In Python: [${codeSpan(library)}](/docs/reference/library#${library}).`);
      for (const cmd of group.operations) out.push(command(cmd, 4, libraryOf(cmd)));
    }
  }

  return {
    title: "The cad command",
    description:
      "Every command of the cad command line, generated from its own help: set-up and updates, the server, running and viewing, and each document type's and integration's operations.",
    markdown: out.join("\n\n") + "\n",
  };
}
