# CAD brief

Read this file when converting a user's request — prose, reference images, technical drawings, or a combination — into a CAD brief. The brief is an internal note-taking scaffold; do not ask the user to fill it out, and do not require the user to provide JSON. If the user supplied JSON voluntarily, extract the same information but continue the workflow in prose notes and build123d source.

## Goal

Convert the request into an actionable modeling brief before writing source or running tools. Every input modality funnels into the same brief; the downstream workflow does not change.

The brief should answer:

- What is being modeled, and is it a part, assembly, modification, inspection task, or secondary output request?
- What dimensions and units are specified, and which missing dimensions are inferable?
- Which features are required?
- Which faces, axes, origins, joints, or interfaces control positioning?
- What output files are requested?
- What must be validated before success is reported?

When inputs conflict, dimensioned sources win over image proportions. When two dimensioned sources conflict — prose says one value, a drawing callout says another — flag the conflict instead of silently choosing.

## Reference images

An image without stated dimensions is design intent, not a spec:

- Establish scale from one stated dimension or a known object in frame; if neither exists and fit matters, that is the one clarification question to ask.
- Estimate remaining proportions from the image and record them as assumptions like any other inferred value.
- Distinguish reproduction ("model this part") from inspiration ("something like this") in the brief; reproduction raises fidelity expectations, inspiration leaves freedom.
- For reproduction, plan a snapshot from the reference image's viewpoint and compare it against the image during visual review.

## Technical drawings

A drawing is a dimensioned contract. Extract it systematically:

- Read the title block and notes first: units, projection convention, revision, disclaimers.
- Identify which view is which — front/top/side, sections, details, iso — and which model axes each maps to before extracting numbers. Trust callouts and view labels, not layout conventions. Section views are the source of truth for internal features: bores, counterbore and blind-hole depths, wall sections.
- Convert every dimension callout into a named parameter and a validation target. Multiplicity (`4X`), `TYP.`, and thread/counterbore/countersink callouts expand into features plus checks.
- Never scale undimensioned geometry off the image. Derive it from stated dimensions when constrained; otherwise assume and report.
- Cross-check features across views; when views disagree, prefer the dimensioned view and flag the conflict.
- Success for a drawing-driven model: every drawing dimension is either verified by `measure`/`refs` after generation or explicitly reported as not verified.

## Brief format

Use concise Markdown notes, not a user-facing structured schema:

```text
CAD brief:
- Model: <part or assembly name>
- Task type: <new part, assembly, modification, inspection, secondary output>
- Inputs: <reference images or drawing views used; omit when prose-only>
- Units: <explicit or assumed>
- Coordinate convention: <origin, base plane, up axis>
- Overall dimensions: <width/depth/height or equivalent>
- Functional features: <holes, slots, ribs, bosses, pockets, shells, text, etc.>
- Manufacturing assumptions: <only when relevant>
- Positioning/mating: <interfaces, datums, child placements, joints, alignment rules>
- Paths: <generator .py, STEP target, secondary outputs if requested>
- Validation targets: <bbox, solid count, labels, spec-driven measurements, refs>
- Assumptions: <only meaningful inferred choices>
```

## Example: simple part

User says:

```text
Make a 100 mm by 60 mm by 6 mm mounting plate with rounded corners, four M4 clearance holes 10 mm in from the corners, and a 20 by 12 mm rectangular cutout in the center.
```

Agent brief:

```text
CAD brief:
- Model: mounting_plate, single STEP part.
- Units: millimeters.
- Origin: center of plate; base plane XY; +Z is thickness direction.
- Body: rounded rectangular plate, 100 × 60 × 6 mm.
- Corner radius: not specified; assume 3 mm.
- Holes: four 4.5 mm M4 clearance through-holes, 10 mm in from each corner.
- Cutout: centered rectangular through-cut, 20 × 12 mm.
- Validation: one positive-volume solid, bbox 100 × 60 × 6 mm, four holes, one center cutout, label mounting_plate.
```

## Example: assembly

User says:

```text
Design a two-piece enclosure, 120 by 80 by 35 mm, with a lid that sits on top and four screw bosses aligned between base and lid.
```

Agent brief:

```text
CAD brief:
- Model: enclosure assembly with base and lid.
- Units: millimeters.
- Assembly origin: center of enclosure footprint; +Z upward.
- Base: hollow lower shell, exterior 120 × 80 mm footprint; height derived from total height minus lid thickness.
- Lid: separate plate on top; assume 3 mm lid thickness unless user gave another value.
- Bosses: four aligned screw bosses; assume M3 unless unspecified dimensions make this unsafe.
- Positioning: base top face and lid bottom face are mating datums; screw axes must align; native build123d joints may be used if they clarify reusable mount points or motion.
- Validation: labeled base and lid children, bbox near 120 x 80 x 35 mm, aligned hole/boss axes.
```

## Clarification policy

Ask one focused question only when the missing information affects fit, safety, compliance, or makes the part impossible to model. Otherwise proceed with assumptions and report them.

Ask when:

- No dimensions are provided for a physical object, and no scale reference exists in the supplied images.
- A mating interface is described but the mating geometry is unspecified.
- The part is safety-critical, load-bearing, pressure-bearing, medical, or compliance-bound.
- The requested output depends on an absent source file or missing imported geometry.

Do not ask when:

- A default clearance hole standard is sufficient.
- A cosmetic fillet radius can be safely assumed.
- Origin/orientation can be chosen and reported.
- The user is asking for a conceptual first-pass CAD model.

## Success criteria

A brief is ready for modeling when it contains enough information to define:

- source file path and STEP target path
- units and local coordinate system
- named parameters
- feature plan and labels
- expected bounding box or key measurements
