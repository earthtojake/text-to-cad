# Specify: a part ready to make

Getting a part ready to machine is deciding what a machinist needs to know that the geometry does
not say: the material, the general tolerance, the surface finish, the edges, which faces it is
located and measured from, what each hole is for. [Specify](https://github.com/pzfreo/specify-core)
(Paul Fremantle's, Apache-2.0) asks those questions of a STEP part, proposes an answer for most of
them from its geometry, and writes the answers into the STEP as AP242 PMI: dimensions with their
tolerances, datums, and the part's general notes. The CAD Viewer shows that PMI in the PMI tab of the
view's panel, beside Model and Position, and draws its dimensions on the part.

Specify is its own command line, `specify-core`, run through `cad run` as below (uv fetches it once,
about 10 MB, and keeps it). Write the command out each time: a variable holding it does not split
into words in zsh, macOS's shell.

The method: **fill in what you can, ask the person only what the part cannot tell you, then write
it.** On a typical part Specify proposes all but one or two answers; the one it cannot propose is
usually the material of an imported STEP.

## 1. Read the part and its questions

```bash
cad run --with specify-core==0.1.17 specify-core analyse -o bracket.analysis.json bracket.step
# {"faces": 14, "features": {"holes": 4, "plates": 2, ...}, "existing_pmi": 0}
cad run --with specify-core==0.1.17 specify-core questions bracket.analysis.json > bracket.questions.json
```

`questions` prints a JSON list. Each question has an `id`, a `prompt`, a `kind` (`choice`, `text`,
`text_list`, `faces`), its `default` (Specify's proposal; null where it has none), its `options` or
`suggestions`, `why` it is asked, and an `attention`:

| `attention` | What it means | What you do |
| --- | --- | --- |
| `required` | Specify has no answer and will not write without one (`part.material`) | Ask the person, unless they already said it or the part's model states it |
| `check` | A proposal worth a look (`datum.A`: which face; `hole.function:...`: what a hole is for) | Check it against the part and the conversation; keep it, change it, or ask if you cannot tell |
| `routine` | A sensible default (`part.general_tolerance` ISO 2768-m, `part.surface_finish` Ra 3.2) | Keep it unless the person or the part says otherwise |
| `refine` | An optional tightening (`datum.A.flatness` none) | Keep it unless asked for |

Never make up an answer to a `required` question. A material, a fit or a finish you guess is a
number on a drawing a shop will make the part to.

## 2. Ask the rest in the chat

Ask every question you could not answer at once, with your question tool (Claude Code's
`AskUserQuestion`, Codex's `request_user_input`): one question per unknown, up to four together.
Write each as Specify's `prompt`, with
up to three options from its `suggestions` or `options` (the likeliest for this part and process
first; a hole's `choices` carry words for each, "A bolt passes through" for `clearance`), a short
header (`Material`), and its `why` where it helps. The person can always type their
own answer instead. Without a question tool, ask in one message that lists the options.

Say first what you filled in: "I filled in 11 of 12 from the part. One I can't tell by looking at it."

## 3. Write it

Save every answer, yours and theirs, as `{question id: value}` beside the part, then write. The
answers you left out take Specify's proposals (`--accept-defaults`):

```bash
echo '{"part.material": "Aluminium 6061-T6"}' > bracket.answers.json
cad run --with specify-core==0.1.17 specify-core write -o bracket.step --accept-defaults bracket.step bracket.analysis.json bracket.answers.json
```

`write` keeps the geometry as it is and adds the PMI, so writing over the part is how it gets its
requirements (`-o` the same path); its JSON says what it wrote (`written`), what it could not
(`not_written`) and its `warnings`. It refuses while a `required` question is open
(`incomplete: 1 question(s) unanswered: part.material`). The answers are kept in the file too, so
the next `analyse` of it starts from them. Then show the part ([Show the model](../SKILL.md#show-the-model)):
the PMI tab lists the material, the general tolerance, the finish and the edges as the part's notes,
and the dimensions are drawn on the part.

A part built from a model is the model's code: run the interview on its STEP export
(`cad model export <id> part.step`), then write the answers into the model with `annotate`, its
material as the body's material ([PMI](pmi.md)), never into the exported file.

## What changed between two revisions

`diff` compares two revisions of a part or an assembly feature by feature, and draws the new one
with what changed coloured:

```bash
cad run --with specify-core==0.1.17 specify-core diff -o tmp/bracket-diff bracket-rev-a.step bracket.step
# tmp/bracket-diff/report.md, report.json, model.png
```

`report.md` reads "4× Ø6 × 8 through holes ...: diameter 6 → 8", "24 × 8 × 8 slot added", the PMI that
changed, and an assembly's parts; `model.png` is its picture. Give the person both. The CAD Viewer
compares two STEP files the same way, in the page: Compare with, in a STEP's file menu.

## Check each change

| The change | Check it with |
| --- | --- |
| The answers | `cad run --with specify-core==0.1.17 specify-core questions bracket.analysis.json --answers bracket.answers.json --open` lists no question whose `attention` is `required` (the rest it lists keep their defaults) |
| The written file | `write`'s `written` names each answer; its `not_written` is empty or said to the person |
| What the viewer shows | The part shown, its PMI tab's notes and dimensions as written |

What a check does not establish: Specify's dimensions are placed under the general tolerance unless
answered otherwise, and its datums are written without a tolerance that names them, which
OCCT-based readers (the CAD Viewer among them) do not show: `write` warns of each.
