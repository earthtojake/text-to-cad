/**
 * /docs/reference/cli, "The cad command": the command line's own description of itself
 * (`cli-reference.generated.json`, `python -m cad_server._internal.cli_reference --docs`, which
 * `scripts/generated/regenerate.py` writes) set as one Markdown page, so the table of contents, the page's
 * Markdown, the search and /llms.txt read it as they read any page. Nothing here is written by hand but the
 * introduction and the groups below:
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
type CliVerb = CliCommand & { types: string[] };
type CliType = { name: string; summary: string; verbs?: string[] };
type CliReference = {
  usage: string;
  verbs: CliVerb[];
  documentTypes: CliType[];
  integrations: CliGroup[];
  commands: CliCommand[];
  texts: string[];
};

export const cli = generated as unknown as CliReference;

// The plain commands, by what a person does with them, in the order each group lists them.
const GROUPS: { title: string; intro: string; commands: string[] }[] = [
  {
    title: "Updates and the installation",
    intro:
      "`cad` installs every newer release of its major version by itself, and `cad plugin install`, which the install command runs, installs and updates the plugin in your agent apps. [Install](/docs/install) says what the install command does, app by app, and how to update and remove.",
    commands: ["cad update", "cad plugin", "cad doctor", "cad cache", "cad telemetry"],
  },
  {
    title: "The server",
    intro:
      "One server runs on your computer, and every command and the viewer go through it. `cad server start` starts it; in the Codex app, the plugin starts it (`cad mcp`).",
    commands: ["cad server", "cad mcp"],
  },
  {
    title: "Running and viewing",
    intro: "",
    commands: ["cad run", "cad viewer"],
  },
];
// A group's commands, each followed by its subcommands (`cad server start` after `cad server`), as the JSON orders them.
const within = (name: string) => cli.commands.filter((cmd) => cmd.command === name || cmd.command.startsWith(`${name} `));

const text = (index: number | string | undefined) =>
  index === undefined ? "" : typeof index === "number" ? (cli.texts[index] ?? "") : index;

const help = { flags: true, dashes: true } as const;
const cell = { flags: true, dashes: true, table: true } as const;

/** The heading id GitHub gives `cad export`: what a link to a command names. */
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
    "`cad` is the command your agent runs, and you can run it yourself. The install command installs it as a uv tool (`uv tool install cad`) and puts its folder on your PATH. One text-to-cad server runs on your computer, which keeps its workers warm between calls.",
    "`cad --help` lists every command, `cad <verb> --help` a verb's forms and every file type's options, and `cad <command> --help` a command's options. This page is that help, generated from the same parser.",
    "```text nocopy\n" + cli.usage.split(" | ").join("\n") + "\n```",
  ];

  // The matrix: each document type's verbs, each a link to its command below.
  const verbs = cli.verbs.map((verb) => verb.command.replace(/^cad /, ""));
  out.push(
    "## Verbs by document type",
    "Each command is a verb and a file: `cad <verb> <file>`. The file's suffix says its type, and each type takes the verbs that make sense for it; a verb its type lacks is refused, naming the types that take it. A model is its `.xbf`, the file its run saves.",
    table(
      ["Type", ...verbs.map((verb) => codeSpan(verb, true))],
      cli.documentTypes.map((type) => [
        codeSpan(type.name, true),
        ...verbs.map((verb) => ((type.verbs ?? []).includes(verb) ? `[✓](#${commandId(`cad ${verb}`)})` : "")),
      ]),
      ["left", ...verbs.map(() => "center" as const)],
    ),
    "## Verbs",
    "Each verb's forms, then every option any type takes: a file's type takes its own, and refuses the rest by name.",
  );
  for (const verb of cli.verbs) out.push(command(verb, 3, libraryOf(verb)));

  const groups = GROUPS.map((group) => ({ ...group, cmds: group.commands.flatMap(within) }));
  const placed = new Set(groups.flatMap((group) => group.cmds));
  groups.push({ title: "Other", intro: "", commands: [], cmds: cli.commands.filter((cmd) => !placed.has(cmd)) });
  for (const group of groups.filter((each) => each.cmds.length)) {
    out.push(`## ${group.title}`);
    if (group.intro) out.push(group.intro);
    out.push(
      table(
        ["Command", "Description"],
        group.cmds.map((cmd) => [`[${codeSpan(cmd.command, true)}](#${commandId(cmd.command)})`, sentence(inline(cmd.summary, cell))]),
      ),
    );
    // A subcommand's heading sits under its command's.
    for (const cmd of group.cmds) out.push(command(cmd, cmd.command.split(" ").length > 2 ? 4 : 3));
  }

  if (cli.integrations.length) {
    out.push(
      "## Integrations",
      "An integration is a tool text-to-cad runs for you. Its own operations on its tool's files are `cad <integration> <operation> <file>`: KiCad's design rule and electrical rules checks, and MuJoCo's compile of a model.",
    );
    for (const group of cli.integrations) {
      const integration = registry.integrations.find((each) => each.name === group.name);
      out.push(`### ${codeSpan(`cad ${group.name}`)}`);
      out.push(sentence(inline(integration?.summary ?? group.summary, help)));
      out.push("```text nocopy\n" + group.usage + "\n```");
      const library = libraryIds.has(`cad.${group.name}`) ? `cad.${group.name}` : undefined;
      if (library) out.push(`In Python: [${codeSpan(library)}](/docs/reference/library#${library}).`);
      for (const cmd of group.operations) out.push(command(cmd, 4, libraryOf(cmd)));
    }
  }

  return {
    title: "The cad command",
    description:
      "Every command of the cad command line, generated from its own help: the verbs on a file, updates and the installation, the server, running and viewing, and each integration's operations.",
    markdown: out.join("\n\n") + "\n",
  };
}
