# Writing a skill

A **skill** is what an agent loads to reach one outcome a person wants: design a CAD part, lay out a
circuit board, describe a robot for simulation, prepare a laser-cut order. It is a folder under
`skills/`, a `SKILL.md` and the references it links, and it ships byte for byte in the plugin.

The skills are the product. Every line of a `SKILL.md` is read by every agent on every task that
loads it, and paid for in the context the agent has left for the work. This guide says what earns a
line, how to keep a skill from growing, and how to test a change.

## What a skill is for

Write for a reader that is a capable engineer who has never seen this tool, and assume that reader
gets more capable every release. It needs three things from a skill, in this order:

1. **The interface.** The commands and their real output, the file and model contracts, the frames
   and units, and the facts it cannot know from training (a nightly KiCad's board does not open in a
   stable KiCad; a model's body is a function of its code and its inputs). This is most of a skill
   and what ages slowest.
2. **The check loop.** How to check each kind of change, and what a clean check does not establish.
   A loop an agent can run lets a stronger model correct itself; a rule it cannot check is a hope.
3. **Strategy that came from evidence.** An order of work or a habit that an agent demonstrably
   got wrong without being told: review a part alone before it is placed; trust a check only after it
   has failed on a planted fault. One or two sentences each.

It does not need engineering it already knows, a step-by-step script for a task it can plan, the
tool's internals, the tool's history, or the same fact twice.

## Short, by judgement

There is no size limit, and none would help: a skill is as long as what most of its tasks need, and a
number invites writing to it. What keeps a skill short is asking, of every line in every change,
whether it earns its place ([Before you add a line](#before-you-add-a-line)), and a reviewer who asks
the same of the diff. The same holds for a reference: it is read less often, not less carefully, so
it carries no history, no internals and nothing said elsewhere.

A skill grows the way the `cad` skill did, to 570 lines with a section on joint stops (which only a
model with a mechanism needs) at its top level: one reasonable paragraph after each feature and each
bug, none of them wrong and none of them weighed against the rest. A pull request that makes a
`SKILL.md` longer says what it weighed.

## Before you add a line

Most bloat arrives one reasonable sentence at a time, each added after a feature or a bug. Ask of
every addition, in this order, and stop at the first yes:

1. **Can the tool say it instead?** If agents keep making a mistake, the command should refuse it
   with a message that says what to do, or `--help` should say it. A refusal is read at the moment it
   matters and costs nothing otherwise. Fix the tool; then the skill needs at most a clause.
2. **Is it already said?** Search the skill and its references. A fact has one home; everywhere else
   links to it. Never restate a reference in `SKILL.md`, or one reference in another.
3. **Does only some work need it?** Then it is a reference's, with one row in "Start with the task"
   pointing at it. A feature most tasks never touch (joint stops, a viewer's panel, a format's
   corner case) is never a section of `SKILL.md`, however large the feature was to build.
4. **Would a capable agent do the right thing without it?** Then leave it out. General engineering
   advice, an explanation of how the engine works inside, a list of what a command prints that the
   output itself shows: none of these change what an agent does.
5. **What is the evidence?** If it passed 1 to 4, the pull request says what an agent did wrong
   without it: a transcript, a telemetry count, a sample's feedback notes. No evidence, no line.

And when a line goes in, look for one to take out: a skill that only ever grows is not being edited.

## Where things go

| It is | It goes |
|---|---|
| What most tasks need: the core loop, the commands, the check table | `SKILL.md` |
| What some tasks need: one feature in depth, a format, a method | A reference, linked from "Start with the task" |
| Every option of a command | The command's `--help`, which the skill points at once |
| What to do after a mistake | The command's refusal |
| How the engine carries something out | The package's READMEs, never a skill |
| What changed between releases | The migration guides, never a skill |
| Why a decision was made | The pull request and [Decisions](decisions.md) |
| How a tool behaves in one agent app | That tool's description, which only agents that have it read |

## A skill is an outcome

Name a skill for what the person is trying to get done, never for a file format, a document type or
a tool.

- **Not a document type.** Several skills write the same kind of file: the `cad` and `pcb` skills
  both write STEP. A document type is the engine's
  ([Adding a document type](adding-a-document-type.md)); a skill teaches the work.
- **Not an integration.** One skill can use several tools, and a tool can serve several skills. How
  a skill drives a tool is one of its references
  ([Adding an integration](adding-an-integration.md)). A tool the agent can run directly is taught
  directly: its own command line, its own Python API through `cad run`.
- **A named service is an outcome.** When a person asks for a service by name (SendCutSend, a Bambu
  printer), the service gets its own skill.
- **Reviewing the work is part of the work.** Checking that a part can be molded belongs to the skill
  that designs it, as a reference, not to a review skill.

Extend an existing skill with a reference unless the new work is an outcome a person would start a
separate conversation for, in words no existing description covers. Prefer few skills: every
installed skill's description sits in the agent's context on every turn, and when the listing
overflows the least-used skills stop triggering.

## Anatomy

```text
skills/<name>/
  SKILL.md            the entry point
  references/*.md     one level deep, each linked from SKILL.md
  agents/openai.yaml  the Codex listing
  LICENSE
```

- **The description** (front matter) decides whether the skill loads at all. Third person, the words
  a person would use for the outcome, what it covers, and what it is not where a neighbouring skill
  could be confused for it. At most 1,024 characters, the format's limit.
- **`SKILL.md`** opens with a few sentences on what the outcome is, then **Start with the task**: a
  table of each task, the command or file to start with, and the reference that goes deeper. A skill
  that makes something has **Check each change**: a table of the kind of change and how to check it,
  then the few rules that decide whether a check showed anything.
- **A reference** opens by saying when to read it, and has a contents list once it is long. It may
  link to another reference, but `SKILL.md` links to every one: a reference reachable only through
  another gets read partially or not at all.
- **No runtime of its own.** A skill runs plain `cad` commands with no version in them. It installs
  nothing and ships no scripts: what a skill would script is a `cad` command or a few lines of Python
  in a code block. It never imports another skill (`test_skill_self_containment.py`).

## Writing it

- Show the real command and its real output, not a paraphrase. Run every example before it ships.
- State facts and say what to do, in short sentences. A reason is worth a clause when it lets the
  agent handle the case you did not write down; an emphatic NEVER is not a reason.
- A number comes from a source: a datasheet, a fab's limits, a measurement, a standard. Say which.
- Say what a check does not establish, so a clean result is not read as more than it is.
- Name only the environment variables a person may set, never one that tunes or debugs the engine.

## Test a large change (A/B)

Most changes to a skill need no bench: a corrected fact, a passage that follows a tool change, a line
added with its evidence or one taken out are reviewed by reading them and running what they say. The
bench is for a change large enough that reading the diff does not say what agents will do: a
`SKILL.md` rewritten, a method changed, a whole section of guidance removed. Before such a pull
request:

```bash
scripts/bench/skill_ab.py --base main                     # every task, both skill sets
scripts/bench/skill_ab.py --base main --task cad-part     # one task
```

It lays out, under `tmp/skill-ab`, one folder per task and skill set (the baseline ref's and the
working tree's), each with its own copy of the skills, its fixtures, a server of its own and a
`BRIEF.md`. Then:

1. **Run one fresh agent per folder** on its `BRIEF.md`, on a model weaker than the one that wrote the
   change: a skill has to work for the least capable model that loads it. Each agent sees only its
   own folder. Keep `runs.tsv`, which says which folder had which skills, from the agents.
2. **Grade against the task's `Expect`**, with your own `cad` commands on what the agent made, never
   the agent's word: the geometry measures what it should, the check passes, the file exists.
3. **Read the agents' skill notes.** What the new text left unclear is the next edit. What both
   versions left unclear is often a tool to fix, not a sentence to add.
4. **Put the table in the pull request**: task, model, correct or not for each side, tool calls and
   tokens, and any difference in what was made. One run a cell is noisy: a difference worth acting
   on is a wrong result or a repeated pattern, not two tool calls. Say which skills no task reached.

The tasks are `scripts/bench/skill_ab/tasks/*.md`: common requests of each skill, each with its
objective answer. Add a task when a skill gains an outcome, when a change rewrites a reference no task
reaches, or when a regression got past the ones there.

## Check a rewrite against what it replaced

A bench task shows that common work still gets done. It does not show what was lost, and a rewrite
loses things in a particular way: two files each drop a "duplicate" on the assumption that the other
keeps it. So before a pull request that shortens a skill:

1. **Run what you keep.** Every command, every example and every claim about what the tool does, on
   the tool at the commit the text ships with. The pass that shortened these skills found about sixty statements that were
   wrong, most of them long-standing: a command that did not exist, an example that could not
   solve, a sign that was backwards.
2. **Audit against the old text, twice.** Have a reader who did not make the change go through the
   previous version passage by passage and look for each fact in the new skill, anywhere in its
   folder, and say where it is now: "moved" is shown by the text it moved to. Then have a second
   reader do the same without the first's account: on the eight `SKILL.md` files the second found
   six slips the first had passed. What goes missing most often is not a fact but its condition
   ("only where there is none", "unless the variable names another"): a sentence shortened until it
   says more than is true. What is no longer there falls into two lists: rightly cut (general
   knowledge, internals, history, what `--help` or a refusal says), and lost (a fact about this tool
   an agent cannot get any other way). Restore the second list, a clause each, and put the first in
   the pull request, where a reviewer can disagree with it.
3. **Fix the tool where the text was a workaround.** A reference that carries a line to step round a
   defect is a report of the defect. The fix and the sentence that relies on it ship in one pull
   request: a skill describes the tool at its own commit, so a rewrite that lands before the fix
   keeps the workaround.

## The shared blocks

Each skill installs on its own, so the few things every skill must say are copied into each, word
for word, and tests keep the copies from drifting:

- **Setup** (`tests/python/global/test_skill_requirements.py`): how to get cad, in every skill that
  runs it, and in no other. It reads, in each (`<VERSION>` is the release):

  ```text
  Written for `cad==<VERSION>`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
  0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

  If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
  https://github.com/earthtojake/text-to-cad
  A project written for an earlier version may need changes; the migration guides say what:
  https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations
  ```

  The release script stamps the version (`scripts/release/sync-version.mjs`); no command carries one.
  0.11.12 is fixed: the first release installed by uv, and `--force` replaces the launcher 0.10.0 to
  0.11.11 wrote. cad updates itself, so the block never has the agent update it. No skill runs the
  install script, and no skill pre-approves a tool (`allowed-tools`). A new skill copies the block
  from one beside it.
  It changes only with a person's approval ([below](#what-changes-only-with-a-persons-approval)).
- **Commands that last** (no test holds this one): a command, an option or a spelling the skills
  stop using keeps working, hidden if need be, for 30 days after the release that stopped using it.
  Say so in the pull request that removes it.
- **Show the model** (`tests/python/global/test_skill_show_the_model.py`): how to show the person what
  was made, in every skill that makes something they look at. It covers an agent with the CAD app's
  tools (`cad_show`) and one without (the page's link).

## What changes only with a person's approval

Three parts of a skill change only with a person's explicit approval, asked for by name: never as
part of a rewrite, a tidy-up or a fix that happens to reach them. Propose the change and wait.

- **The Setup block.** It is what every agent runs first, on every computer, and it installs
  software: a wrong word in it breaks every skill at once, for people whose cad may no longer be
  able to fetch the correction. The release's version stamp is the one change made without asking.
- **The front matter's `name` and `description`.** The plugin knows its skills by name, so a renamed
  skill orphans every installed copy. The description decides whether the skill loads at all, and
  sits in every agent's context on every turn beside every other skill's. The A/B bench hands an
  agent its skill, so it does not test this: propose a description with the requests it should and
  should not load for.
- **A line that says what the agent does not do on a person's behalf** (start a print, place an
  order, spend money). Adding one, removing one and weakening one are each a decision about the
  product, not wording.

## Checklist

- [ ] The skill is an outcome a person asks for, and no existing description covers it.
- [ ] Each added line passed [Before you add a line](#before-you-add-a-line), and the pull request
      says what an agent got wrong without it.
- [ ] `SKILL.md` opens with "Start with the task" and links every reference; a change that made it
      longer says what was weighed.
- [ ] A skill that makes something has "Check each change".
- [ ] Every example was run, and every command in a code block parses.
- [ ] The Setup and Show the model blocks are the shared text where they apply.
- [ ] The Setup block, the `name` and `description`, and every line on what the agent does not do on
      a person's behalf are as they were, or a person approved the change by name.
- [ ] A rewrite or a change of method was run A/B, with the table in the pull request, and a
      rewrite was audited against the text it replaced.
- [ ] A command the skill stops using still works for 30 days.
- [ ] Its name is in `SKILLS` in `packages/cad/src/cad_server/plugin/source.py`, in the same release (a
      skill taken out moves to `RETIRED_SKILLS`): the names `cad plugin install` takes as ours. A copy
      under a name it does not know is someone else's, never replaced or removed
      (`tests/python/global/test_plugin_knows_the_skills_shipped.py`).
- [ ] A new skill is linked from the README's Features and the docs site's (`features` in
      `apps/docs/src/lib/content.ts`), and named in `.muse-plugin/plugin.json`.
- [ ] Its page in the docs site's Skills says for a person what the skill is: what it makes, how it
      works and where it stops (`apps/docs/content/skills/<skill>.md`, at `/docs/<skill>`, in the map
      `apps/docs/src/lib/docs/nav.ts`; its feature's `page` links it). A change to what the skill
      does or teaches is made there too.
