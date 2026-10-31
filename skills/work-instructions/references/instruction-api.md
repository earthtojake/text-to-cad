# `cadgen.work_instruction` reference

```python
from cadgen.work_instruction import (
    work_instruction, Instruction, Format, Spec, Drawing, Datasheet, Stated,
    Cited, Unspecified, Torque, Material, Adhesive, Cure,
)
```

## Template

Every document, product and value below is a PLACEHOLDER showing the script's
shape: `PS-XXXX`, `ADHESIVE-X` and the `<...>` values are not real, and none
of them is a default. A real script carries only what the user's documents
state, each value copied from the section it cites. A value they do not state
is left out, and prints NOT STATED.

```python
from bracket_assembly import bracket_assembly  # the assembly's model, beside this script
from cadgen.work_instruction import (
    Adhesive, Cited, Cure, Datasheet, Drawing, Instruction, Material, Spec,
    work_instruction,
)

# The documents, as the user supplied them: number, title, revision.
FASTENING = Spec("PS-XXXX", "<fastening spec title>", revision="<rev>")
BONDING = Spec("PS-YYYY", "<bonding spec title>", revision="<rev>")
TDS = Datasheet("ADHESIVE-X", revision="<rev or date>")
DWG = Drawing("DWG-ZZZZ", revision="<rev>", title="<drawing title>")

# Each process record once. Prep comes from the bonding spec (the record's
# per=); the spec defers mixing to the manufacturer, so mix cites the data
# sheet. Pot life is left out: neither document the user gave states it, so
# it prints NOT STATED.
ADHESIVE = Adhesive(
    "ADHESIVE-X",
    prep="<prep as PS-YYYY section 5.1 states it>",
    mix=Cited("<mix ratio as the data sheet states it>", per=TDS.at("Mixing")),
    cure="<cure as PS-YYYY section 5.1 states it>",
    per=BONDING.at("5.1"),
)
LOCKING = Material("<threadlocker>", per=FASTENING.at("<section>"),
                   note="<how it is applied>")


# out= is relative to this script: a project with PDF/ beside src/.
@work_instruction(out="../PDF/bracket_assembly_wi.pdf")
def bracket_assembly_wi():
    wi = Instruction(
        bracket_assembly(),  # the model's document; an assembly with no model: its .xbf or .step
        title="BRACKET ASSEMBLY", number="WI-0001", revision="A", drawing=DWG,
        rigor="production",   # prototype, production or controlled: as asked
        emphasis="visual",    # visual or process: as asked
        # format=Format(...), # only if the user gave a template or example
        scope="<what this builds, as the user puts it>",
        safety=["<PPE and hazards, as the user's documents state them>"],
        tools=["<fixture the user names>"],
    )
    wi.operation("Prepare")
    wi.step("Load the base plate on the fixture", install=["base_plate"])

    wi.operation("Bond the bracket")
    (wi.step("Bond the bracket to the base plate", install=["bracket"],
             camera="bottom")
       .caution("<caution, in the user's words>")
       .bond(ADHESIVE, surfaces=["bracket/face 5"]))
    wi.step("Cure the bond").cure(
        Cure("<cure name>", cycle="<cycle as stated>", per=BONDING.at("<section>")))

    wi.operation("Install the pin")
    (wi.step("Install the pin", install=["pin"])
       # Once stated: torque=Torque(<low>, <high>, unit="in-lbf", per=FASTENING.at(...)),
       # or per=DWG.at("<note>") where a drawing callout differs from the table.
       .fasten("<nut part number>", qty=1, torque=None, locking=LOCKING)
       .inspect("<acceptance criterion as stated>", per=DWG.at("<note>"),
                record="<measured value, unit>"))
    return wi


if __name__ == "__main__":
    bracket_assembly_wi()
```

## `@work_instruction(out="<path>.pdf")`

Declares the instruction. The function returns an `Instruction`; calling it
writes one PDF at `out` (relative to the script), prints every open item, and
returns `[path]`. A refused or failed run writes no file at `out`; an earlier one
there is left as it was.

## `Instruction(assembly, *, title, number, revision, ...)`

| Argument | Meaning |
| --- | --- |
| `assembly` | the assembly's document: what calling its model returns, or an `.xbf` or `.step` path; a single part is refused |
| `title`, `number`, `revision` | the instruction's own; on every page |
| `part_number`, `author` | optional; the author signs "prepared by" |
| `drawing` | the assembly `Drawing`, first under APPLICABLE DOCUMENTS |
| `status` | `draft` (default, DRAFT on every page) or `released` (refused while anything is open) |
| `size` | `LETTER` (default) or `A4`, portrait |
| `camera` | every figure's camera: `iso` (default), `front`, `back`, `left`, `right`, `top`, `bottom` |
| `pictures` | `False` writes no figures, so the engine draws nothing |
| `scope` | one sentence: what this builds and when it applies |
| `safety` | lines of PPE and hazards, as the user's documents state them |
| `tools` | fixtures and tooling the user names, listed under EQUIPMENT |
| `revisions` | `(rev, date, change)` rows |
| `rigor` | `prototype`, `production` (default) or `controlled`; see below |
| `emphasis` | `visual` (default) or `process`; see below |
| `format` | a `Format` read from the user's template or example; see below |

`wi.operation(title)` starts the next operation: a heading row over the steps
after it and a line in the front pages' overview. Steps keep one sequence
across operations.

`wi.step(title, *, install=(), camera=None, picture=True, frame="step")` adds
the next step and returns it. One step is one action. `install` names the
parts the step puts in place: a label (every part carrying it), or a
subassembly's label or ref (`wheel`, `cart/wheel.2`), which installs it as ONE unit
(one line in the parts list) and every part under it in the figure. The parts
list puts parts on one line only when they carry the same label: give copies
of one part one label (`pin`), not numbered names (`pin_1`, `pin_2`). A part is
installed by one step only. `frame="step"` fits the figure to the parts the
step installs with room around them; `frame="assembly"` fits the whole
assembly. A step that installs nothing (a cure, an inspection) still has a
figure of what is installed so far, and none while nothing is.

`wi.tree()` returns every part and subassembly, indented, by its ref (the
grammar `cadgen inspect` and the viewer use: a label, numbered among siblings
that share it, `pin.2`, or a path where the label alone names several,
`arm/pin`): what `install=` takes, beside a part's label. Print it before writing the steps.

`wi.open_items()` returns what the run prints: each NOT STATED value, each
inspection criterion with no source, each value free text states with no
source (below), and each part no step installs.

## Rigor, emphasis and a house format

| `rigor` | Sign-off columns | Paperwork | Inspections |
| --- | --- | --- | --- |
| `prototype` | DONE | none: no work order, lot, actual-reading or calibration blanks, no approvals, no close-out | a row like any other |
| `production` | TECH | work order, serial and start; lot and expiry; actual readings; equipment ID and cal due; prepared and approved; a close-out | a row like any other; a criterion's source is printed when given |
| `controlled` | TECH, QA | production's, with reviewed by | a hold point (HOLD in the last sign-off column); a criterion with no source is an open item |

`emphasis="process"` drops the figure column (and renders no figures) and adds
PROCESS REFERENCES to the front pages: each cited section of each document,
with the steps that apply it.

`Format(*, title, company, step_label, numbering, stamps, approvals,
instruction_label, figures)` is the
company's own layout, read from the template or example the user gave. Every
field is optional: give only what that document shows, and the rest keeps the
rigor's layout.

| Field | Means | Example |
| --- | --- | --- |
| `title` | what the document calls itself | `"ASSEMBLY PROCEDURE"`, `"TRAVELER"` |
| `company` | printed in every header | `"Acme Aerospace"` |
| `step_label` | the step column's heading | `"OP"`, `"SEQ"` |
| `numbering` | `sequential` (1, 2, 3) or `by-ten` (10, 20, 30) | `"by-ten"` |
| `stamps` | the sign-off columns, left to right; a hold point uses the last | `("MECH", "INSP")` |
| `approvals` | the signature roles on the front pages | `("Written by", "Quality")` |
| `instruction_label` | the instruction column's heading | `"OPERATION DESCRIPTION"` |
| `figures` | `False` when the template has no figure column | `False` |

## Step operations

Each returns the step, so they chain, and prints in the order called.

| Method | Prints | The floor records (from `production` up) |
| --- | --- | --- |
| `instruct(text, *, per=None)` | the user's words, or a document's (cited); a value in it with no `per` is an open item | |
| `not_stated(what)` | `what` with NOT STATED: something the step needs that nobody has stated; an open item | |
| `fasten(hardware, *, qty=None, torque=None, locking=None, sequence=None, surfaces=())` | hardware, torque (NOT STATED when `None`; as said for an `Unspecified`), threadlocker, sequence (text, or `Cited`: a value in it is cited) | actual torque, one per fastener up to 8 |
| `bond(adhesive, *, surfaces=())` | adhesive, prep, mix, pot life, cure, the surfaces named | prepared at, adhesive lot, expiry, mixed at, mated at |
| `cure(cure)` | the cycle | oven or autoclave ID, start, end, chart no. |
| `apply(material, *, surfaces=())` | a sealant, primer or other consumable and how it goes on | |
| `inspect(text, *, per=None, record=None)` | an inspection; when `controlled`, a hold point whose criterion with no `per` prints NOT STATED and is an open item (at any rigor when it states a value) | the measured value `record` names |
| `warning(text, *, per=None)`, `caution(...)`, `note(...)` | a box above the step, in the user's words or a document's (cited); a value in it with no `per` is an open item | |

`bond` and `cure` take `None` for a record nobody has stated yet; it prints
NOT STATED. `surfaces` (on `bond`, `apply` and `fasten`, where it marks the
faces hardware the model does not carry goes into) are face refs (`bracket/face 3`, or the `bracket/f:...` ref the viewer
copies; `cadgen inspect "$ID" "bracket/face 3"` says which face it is), each resolved
to exactly one face when the step names it and drawn on the step's figure;
each must be on a part installed by that step or before.

## Sources

Every record and every torque takes `per=`, and nothing else is accepted:

| Source | Prints | For |
| --- | --- | --- |
| `Spec(number, title, revision=).at(section)` | `PS-2001 Rev D §4.2, Table 3` | a rule of the company's process spec |
| `Drawing(number, revision=, title="").at(callout)` | `DWG-1042 Rev B, note 4 (drawing callout)` | a requirement the drawing states, including a deviation from the spec |
| `Datasheet(product, revision=).at(section)` | `EA 9394 datasheet, 2019-05, Mixing` | a manufacturer's data sheet the spec defers to |
| `Stated(by, on=date)` | `stated by A. Zhou, 2026-10-23` | something the user said, and only that |

A record's `per` covers every field. A field from a different document is
`Cited(text, per=...)` in place of the plain text, and prints its own source.
A citation prints once for the lines of one operation it covers; the next
operation prints its own, even from the same section.

Free text that states a value -- a number followed by a unit of
`VALUE_UNITS` (`45 in-lbf`, `0.5 mm`, `150 °F`, `30 min`, `50%`) or a ratio
(`100:17`) -- cites it as a record does: `per=` on `instruct`, `inspect` and
the notices, `Cited(text, per=...)` for a `fasten` sequence and for a `scope`
or `safety` line. Without one its
source prints NOT STATED and is an open item, so a released instruction
refuses it. A step's title cites nothing: a value goes in the operation
that cites it ("Fasten the bracket", then `fasten(..., torque=Torque(...))`),
never in the title.

`Unspecified(text, *, per)` is a value that does not exist, as the user says
("Snug; no torque is specified"), in place of a `Torque`. It prints as said
with its source, is not an open item, and needs no torque wrench. A value that
exists but nobody has stated is left out instead, and prints NOT STATED.

## Records

A field left out prints NOT STATED if it is required, and nothing if optional.

| Record | Required | Optional |
| --- | --- | --- |
| `Torque(low, high=None, *, unit, per)` | `low` and `unit` (`in-lbf`, `ft-lbf`, `N-m`) | `high` for a range |
| `Adhesive(name, *, prep, mix, pot_life, cure, per)` | `prep`, `mix`, `pot_life`, `cure` | |
| `Cure(name, *, cycle, per)` | `cycle` | |
| `Material(name, *, per, note)` | | `note` |

Values are text as the document writes them (`"100:17 by weight"`,
`"3000 rpm"`): nothing is parsed, converted or rounded; a torque prints the
numbers given. Adhesives and threadlockers are listed under
MATERIALS with lot and expiry blanks; a torque wrench and an oven are listed
under EQUIPMENT with ID and calibration-due blanks.

## The figures

One snapshot job draws every step's figure through the engine. Each shows the
assembly as it stands after the step, as hidden-line art (black edges): parts
a later step installs are left out, parts installed earlier are lines only,
the step's own parts are filled blue, and named surfaces are outlined purple.
Each figure looks from the instruction's `camera` (or the step's own) and is
placed exactly, never fitted to what is visible. `frame="step"` (the default)
centres it on the step's parts, so the view moves from step to step;
`frame="assembly"` fits the whole assembly, one camera for every such figure,
so a part stays in place across them.

## What the run prints

| Line | Meaning |
| --- | --- |
| `open item: step 2 (bond): pot life not stated` | a value the documents or the user still owe |
| `open item: step 4 (inspect): criterion source not stated` | an inspection with no document behind it |
| `open item: step 3 (caution): source of 45 in-lbf not stated` | a value written into free text with no source |
| `open item: assembly/pin.2: no step installs it` | a part the order leaves out |
| `wrote <path> (N pages)` | the PDF |

A step taller than a page is refused, naming the step: split it into shorter
steps.
