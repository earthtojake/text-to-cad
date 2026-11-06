# Writing a skill

A **skill** is what an agent loads to reach one outcome a person wants: design a CAD part, lay out a
circuit board, describe a robot for simulation, prepare a laser-cut order. It is a folder under
`skills/`, a `SKILL.md` and the references it links, and it ships byte for byte in the plugin.

This guide is how we decide what a skill is, what goes in it, and how it is written. The rules that
keep skills installable on their own are AGENTS.md's **Repo Rules**; the tests that pin the shared
blocks are under `tests/python/global/`.

## A skill is an outcome

Name a skill for what the person is trying to get done, never for a file format, a document type or
a tool.

- **Not a document type.** Several skills write the same kind of file: the `cad` skill and the `pcb`
  skill both write STEP. A document type is the engine's ([Adding a document type](adding-a-document-type.md));
  a skill teaches the work that produces it.
- **Not an integration.** One skill can use several integrations (the `pcb` skill uses KiCad's command
  line and KiPy), and an integration can serve several skills. How a skill drives a tool belongs
  inside the skill, usually as one of its references ([Adding an integration](adding-an-integration.md)).
- **A named service is an outcome.** When a person asks for a service by name (SendCutSend, a Bambu
  printer), that name is what the agent hears, so the service gets its own skill.
- **Reviewing the work is part of the work.** Checking that a part can be molded or a board can be
  fabricated belongs to the skill that designs it, as a reference, not to a separate review skill.

### Add a skill, or extend one?

Extend an existing skill with a reference unless the new work is an outcome a person would start a
separate conversation for, in words the existing descriptions do not cover. Prefer few skills. Every
installed skill's description sits in the agent's context on every turn, and agents share a budget
for them (about 1% of the context window): when the listing overflows, the least-used skills lose
their descriptions and stop triggering.

## Anatomy

```text
skills/<name>/
  SKILL.md            the entry point, under 500 lines
  references/*.md     one level deep, each read only when SKILL.md sends the agent there
  scripts/            thin entrypoints, when the skill has any (their behaviour lives in cad_server.cli)
  agents/openai.yaml  the Codex listing
  LICENSE
```

- **The description** (frontmatter) decides whether the skill loads at all. Lead with the words a
  person would use for the outcome, name what it covers, and say what it is not when a neighbouring
  skill could be confused for it. Keep it to about 300-450 characters.
- **SKILL.md** opens with a sentence or two on what the outcome is, then a "Start with the task"
  table: each task the skill covers, the command or file to start with, and the reference that goes
  deeper. Everything an agent needs on most runs is in SKILL.md; everything else is a reference.
- **References** are one level deep. A reference that sends the agent to another reference gets read
  partially or not at all.
- **No runtime of its own.** A skill that uses the server runs the `cad` command and names no
  release. It installs nothing: no `requirements.txt`, no vendored packages. Code a skill needs is
  the library's or the server's, reached by a command or an import.
- **Independent of other skills.** A skill never imports another, and never puts `skills/` or the
  repository root on a lookup path. Each installs alone through the Skills CLI.

## What goes in a skill

Three kinds of content. Use them as a lens when editing, not as a template: a skill needs no
section named for each.

1. **The interface**, most of the text: the commands and their real output, the file and model
   contracts, the coordinate frames and units, and the gotchas an agent cannot know from training (a
   nightly KiCad board does not open in a stable KiCad; a body is a function of its code and its
   inputs). This is what ages slowest and what agents need most.
2. **The check loop.** Every skill that makes something says how to check each change, in a section
   called **Check each change**: a table of the kind of change and how to check it, then the few rules
   that decide whether a check showed anything. A loop an agent can run is what lets a stronger model
   correct itself; an instruction it cannot check is a hope.
3. **Method**, only where it is not obvious and comes from evidence: an expert's way of working that a
   capable model would not reach on its own, such as placing a board one functional group at a time
   and routing octolinear by hand. Pair each method with a check that measures it (the layout
   reference's property script). Leave out general engineering advice a model already knows: as
   models improve, this is the part to cut first.

### Writing it

- Show the real command and its real output, not a paraphrase.
- A number comes from a source: a datasheet, a fab's limits, a measurement, a standard. Say which.
- Say what a check does not establish, so a clean result is not read as more than it is.
- Write rules as what is true and what to do, plainly. Do not repeat a rule in two places in one skill.
- When a skill changes what an agent does, say in the PR what the old and the new text was.

## The shared blocks

Each skill installs on its own, so the few things every skill must say are copied into each, word
for word, and tests keep the copies from drifting:

- **Setup** (`tests/python/global/test_skill_requirements.py`): how to get the `cad` command, in every
  skill that runs the server, and in no other.
- **Show the model** (`tests/python/global/test_skill_show_the_model.py`): how to show the person what
  was made, in every skill that makes something they look at.

Show the model covers both kinds of agent. One with the CAD app's tools calls `cad_show`, whose
description, and those of the tools beside it, say how each host shows a model; one without them
gives the person the page's link from the command line. How a tool behaves on a host belongs in that
tool's description, which only agents that have the tool read, never in a skill.

## Checklist

- [ ] The skill is an outcome a person asks for, and no existing skill's description already covers
      it (otherwise, a reference in that skill).
- [ ] The description leads with the person's words and stays within about 450 characters.
- [ ] SKILL.md is under 500 lines, opens with the "Start with the task" table, and every reference is
      one level deep.
- [ ] It has a **Check each change** section, and every method it teaches has a check.
- [ ] The setup and Show the model blocks are the shared text, word for word, where they apply.
- [ ] It installs nothing and imports no other skill.
- [ ] A feature in README.md's Features and the docs site's (`features` in
      `apps/docs/src/lib/content.ts`, the same list) links it, and `skills.sh.json` lists it.
