# Design intent, tolerances and GD&T

A drawing is a contract: what it states is what a shop makes and an inspector
measures. Which dimensions matter, how tightly, and from which faces depends on
how the part is used and how far along it is, and only the person knows that.
So ask before dimensioning, propose what you think matters, and write into the
drawing script only what they confirm.

## The interview

Ask one thing at a time, in plain words with the standard term in brackets.

1. **Stage and use.** Is this a concept to talk over, a prototype, or for
   production? Who makes it (a machine shop, a 3D printer, a molder)? What does
   the part mount to, what moves against it, what has to fit? Ask whether their
   company has its own drawing format (a profile, below).
2. **Name the critical interfaces, then propose what matters, one numbered
   item at a time,** read off the part (and, for an assembly, off where parts
   meet: a pin in a bushing in a bore is two fits):
   - the faces it locates on, the ones it is bolted or clamped down by
     (datums A, B, C)
   - pin and fastener holes (position, to those datums)
   - bores that take a bearing, bushing or pin (a fit: H7 and the like)
   - sealing, sliding and mating faces (flatness, perpendicularity, a finish)
   - what can be loose (the general tolerance covers it)

   Show each one: a picture of the part with that feature marked (below). An
   assembly's part is shown in place, the rest faded (`--focus`).
3. **The person confirms, changes or removes each item.** They may click the
   face they mean in the CAD viewer and paste its reference instead. A standard
   fit (ISO 286) may be suggested by name; a number is never applied without a
   yes.
4. **Write only confirmed values** into the drawing script, as ordinary calls:
   `tol=`, `fit=`, `basic=True` and a `Frame`, `view.datum(...)`,
   `parts.set(...)`. The script is the record of the interview: rerun it after
   a model change and nothing is asked again. Anything not confirmed stays
   blank, and the run reports it.
5. **For an assembly, go joint by joint.** A first run of the set lists them
   in its `interface:` lines: each pin in a bore with its clearance at nominal
   sizes, and each pair of faces that touch with no end play. For each joint,
   ask what it does (turns, slides, locates or stays fixed), which decides the
   fit on both parts; how it is held (a torque, a threadlocker grade, a press
   fit, a bond and its cure, a weld, a retaining ring, nothing at all), which
   is a flag note (`view.flag(..., joint=...)`); the end play it needs; and
   for a moving joint, its stroke and the mounting distances at each end of
   it. How: [joints and interfaces](assemblies.md#joints-and-interfaces).
6. **Choose the controlling dimensions, and how they run.** These are design
   intent; the model cannot say them, so propose and ask, never assume:
   - **Baseline or chain.** Positions that matter measured from one datum face
     (baseline, or parallel, dimensioning: tolerances do not add up), or the
     spacing between neighbours where that is what matters (chain: a hole
     pitch). Many features, a hole table or ordinates.
   - **What is reference.** A size the others add up to is stated twice once
     it is toleranced: say which one matters (the fit, the gap, the mounting
     distance) and make the derived one reference, or leave it out. The run's
     `redundant:` lines name every loop it finds.
   - **The tolerances themselves**, size by size, from the person or a standard
     fit they confirm by name.

### Refreshing a drawing

A drawing script that already exists records where the requirements stood
when it was written. Before regenerating it after a model change, or showing
it to someone, read its stage and the `requirements:` line of its last run. A
`concept` stage, or sizes that are all nominal, is not a decision that they
stay that way: name the interfaces still without a requirement and ask
whether to settle them now. When the point of the drawing is to show
tolerancing, a nominal drawing cannot show it; say so before redrawing it.

### The handoff

Report geometry and requirements apart. Geometry is what the sheet locates
and sizes, what its `incomplete:` and `redundant:` lines still name, and which
parts are drawn simplified. Requirements are what its `requirements:` line
counts: sizes toleranced, basic, reference and nominal, the datums and frames,
and the interfaces with no fit, tolerance or position; for an assembly, each
`interface:` joint and what was decided about it. A sheet can locate and size
every feature and tolerance none of them; say both.

### A picture per question

Mark the feature with an annotation and render it with `cadgen snapshot`. An
annotation is JSON in model millimetres: a closed `stroke` round the feature
(points on its edge, x y z triples), and a `text` mark with its number (four
corner points, in the plane the label should face).

```json
{
  "units": "mm",
  "marks": [
    {"id": "bore", "kind": "stroke", "color": "#d9480f", "width": 4, "closed": true,
     "points": [6, 0, 10, 4.24, 4.24, 10, 0, 6, 10, -4.24, 4.24, 10, -6, 0, 10, -4.24, -4.24, 10, 0, -6, 10, 4.24, -4.24, 10]},
    {"id": "label", "kind": "text", "color": "#d9480f", "text": "2", "fontPx": 28,
     "points": [8, 8, 10, 14, 8, 10, 14, 14, 10, 8, 14, 10]}
  ]
}
```

```bash
# ID: the id: line `python clevis.py` printed (an xbf or STEP path works too)
cadgen snapshot "$ID" tmp/intent/2-bore.png --camera iso --annotation tmp/intent/2-bore.json
cadgen snapshot "$RIG_ID" tmp/intent/3-pin.png --camera iso --display '{"mode": "shaded", "isolated": ["pin.2"]}'
```

`isolated` takes part refs, an occurrence's path of names: a parts list item's
`.refs`.

Name the pictures by item and show them beside each question.

## Three kinds of dimension

| Kind | Call | Prints | Means |
| --- | --- | --- | --- |
| toleranced | `tol=0.1`, `tol=(0.05, 0.02)`, `fit="H7"`, `limits=(39.98, 40.02)` | `40 ±0.1`, `40 H7`, the two limits | inspect it to this |
| basic | `basic=True` | `40` in a box | the exact target; a GD&T frame bounds the feature |
| reference | `reference=True` | `(40)` | information only, never inspected; an assembly's envelope |

Every stated value prints exactly as given (`tol=0.005` prints `±0.005`),
to at most four decimal places; a value needing more is refused, never
rounded. A dimension with none of these is governed by the general tolerance
or the general profile. A basic dimension with no frame on its sheet is reported:
nothing bounds it. `diameter()` and `radius()` take `basic` and `reference`;
`overall(reference=True)` makes both overall sizes reference.

## Frames and datums

```python
from cadgen.eng_drawing import Frame

front.datum("A", (0, -25, 0))                  # the face it bolts down on
top.datum("B", (-40, 0, 10))                   # the edge it is pushed against
top.hole((20, 0, 10), frame=Frame("position", 0.1, ("A", "B"), diameter=True, modifier="M"), key=True)
top.dim((-40, 25, 10), (20, 25, 10), basic=True)   # the hole's true position from B
front.frame((0, -25, 10), Frame("flatness", 0.05)) # a free frame on a surface
```

- `Frame(characteristic, tolerance, datums=(), diameter=False, modifier=None)`.
  Characteristics, in ASME Y14.5-2018's order: `straightness`, `flatness`,
  `circularity`, `cylindricity` (form, no datums); `line_profile`,
  `surface_profile`; `angularity`, `perpendicularity`, `parallelism`
  (orientation, datums required); `position`, `concentricity`, `symmetry`
  (the last two are ISO 1101's; Y14.5-2018 dropped them, so a sheet whose
  profile follows it refuses them and names what to state instead);
  `circular_runout`,
  `total_runout` (datums required). `diameter=True` (a cylindrical zone) and
  `modifier="M"` or `"L"` (material condition) only where they apply; anything
  else is refused, with the rule.
- `view.datum(letter, point, offset=None)` stands a datum feature symbol on the
  face through `point`, out by the nearest side of the view. `datum=` on
  `hole`, `slot`, `dim` or `diameter` makes that feature of size the datum.
  Letters I, O and Q are refused, and a letter names one feature per sheet.
- A frame naming a datum no view of its sheet defines (a detail of it counts) is
  refused, naming the sheet.
- A frame on a sheet with no `profile=` is refused: ISO GPS and Y14.5 read one
  frame differently, so the sheet names its standard (`profile=GENERIC` for ISO
  GPS, or a company's own `Profile`), and the profile's note prints it.
- `frame=` on a hole, slot or diameter callout hangs the frame under its text;
  on a `dim`, beyond its value. `key=True` marks a key characteristic with the
  profile's boxed letters.
- `Sheet(general_profile=Frame("surface_profile", 0.2, ("A", "B", "C")))` is
  note 1, `UNLESS OTHERWISE SPECIFIED, ALL SURFACES` and the frame: every
  surface the drawing does not control one by one is within that profile.
  Then dimension features with basic dimensions and give the ones that need
  more their own frames.

## Stages

`Sheet(stage=...)` is `"concept"`, `"prototype"` or `"production"`. It prints
in the title block and sets what the completeness report asks a part's sheet
to define:

| | Concept | Prototype | Production |
| --- | --- | --- | --- |
| Tolerance | nothing asked | a general tolerance or general profile | datums, and a general profile or general tolerance |
| Material | nothing asked | the material | the material and its spec, and the finish |
| Key characteristics | none | none | asked whether any feature is one (a note) |
| Title block | CONCEPT, NOT FOR MANUFACTURE | PROTOTYPE | PRODUCTION |

A concept drawing need not be finished: nominal sizes are fine. Keep GD&T off
concept and prototype drawings unless the person asks for it.

**Linear tolerances or GD&T.** A simple part keeps linear (±) tolerances: a
shop checks it with calipers and a micrometer, which costs less than a CMM.
Propose GD&T where the function needs it: a complex part, features that must
locate together (a hole pattern to its mounting faces), or a form or
orientation a ± cannot control (flatness of a sealing face,
perpendicularity of a bore to its mounting face). Say which, and why, item
by item.

## Profiles

A profile is a company's or an industry's conventions, never its numbers:

```python
from cadgen.eng_drawing import GENERIC, Profile

aero = Profile("EXAMPLE AERO", "ASME Y14.5-2018", fields=("CAGE CODE", "DISTRIBUTION"))
Sheet(stage="production", profile=aero, company="EXAMPLE AERO CO.",
      fields={"CAGE CODE": "0ABC1", "DISTRIBUTION": "D"},
      material="AL 7075-T7351", spec="AMS 4078", finish="ANODIZE PER MIL-A-8625 TYPE II",
      general_profile=Frame("surface_profile", 0.2, ("A", "B", "C")), general_tolerance="±0.1")
acme = Profile("ACME", "ASME Y14.5-2018", {"TYPE A": "concept", "TYPE B": "prototype", "TYPE C": "production"},
               characteristic_mark="CC")
Sheet(profile=acme, category="TYPE B")          # prints TYPE B, checked as a prototype
```

- `standard` is `"ISO GPS"` (ISO 8015, ISO 2768 or 22081 general tolerances,
  ISO 1101 frames) or `"ASME Y14.5-2018"`. One drawing is read by one
  standard: a general tolerance from the other is refused. The profile writes
  its standard's note; under ISO, `general_tolerance` names a standard and
  class ("ISO 2768-m"); under ASME, it states the values ("±0.1").
- `categories` maps a company's own category names to stages.
- `fields` adds title-block cells, blank until `Sheet(fields=...)` fills them.
- `characteristic_mark` is the boxed letters a key characteristic carries
  ("KC"; AS9103 leaves the symbol to the customer).

`GENERIC` follows ISO GPS. A company writes its own `Profile` in its project, as
`aero` above: an aerospace one adds CAGE CODE and DISTRIBUTION (the distribution
statement's letter; its wording goes in a note).

A material spec to suggest follows the industry: SAE AMS for aerospace, ASTM for
general commercial work, EN in Europe. It depends on the product form too (AMS
4027 is 6061-T6 sheet and plate; bar and forgings have others), so ask the form
before suggesting one.

With no stage and no profile, the drawing is as it always was: no band on the
title block, nothing asked of it beyond the features it leaves undimensioned.
