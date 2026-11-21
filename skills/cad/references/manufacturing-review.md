# Manufacturing checks: the result, the review, a redesign

Read this file for a manufacturing check's result in full, a shop's own limits, a review or a
redesign. It is what every process shares: SKILL.md's [Can it be made?](../SKILL.md#can-it-be-made)
says when a check runs, and each process's reference what is particular to it.

- [The check](#the-check)
- [A shop's own limits](#a-shops-own-limits)
- [Read the result](#read-the-result)
- [The review](#the-review)
- [Check a redesign](#check-a-redesign)

## The check

A model, a STEP or an xbf is measured exactly, each finding at a face or edge ref; a mesh (STL, 3MF,
GLB) as triangles, each finding at `x, y, z` in millimetres.

Check a part by its own id: each part model has its own document. An assembly's check judges every
part as it stands there, and a part used several times each way it stands (a print's overhangs and a
molding's draft turn with it): an occurrence turned another way has findings of its own, at its own
ref, and the totals count every occurrence.

In a check script the same check is `cad.model.dfm(handle, ...)`, `cad.step.dfm(path, process=...)`
or, on a live build123d shape, `cad.build123d.dfm(shape, process=...)`. The options go by name, numbers
as numbers (`tools=[3, 6]`, `strict=True`), and the result is data: `result.status`, `.findings`,
`.measurements`.

## A shop's own limits

Each process has one table of rules: general practice from published design guides, and text-to-cad's
own floors where no guide states a limit. A finding's `source` says which, and none is a shop's: no
option picks a shop's rule set. What the person knows of their shop goes in as the process's options
(its reference lists them), and a shop's other limits are compared with `measurements.<family>`, which
every result carries.

A specification the person supplies overrides every rule: compare its numbers with the measured
figures and cite it. Where two specifications conflict, record both rather than choosing.

## Read the result

`cad model dfm "$ID" --tools 3,6,10`, on a plate whose pocket corners are 0.5 mm:

```text
error: cnc.internal_corner_radius, 4 place(s). Hint: radius the corner to at least 1.5 mm, the smallest tool's radius, or add a smaller tool. Source: Protolabs Network (Hubs), How to design parts for CNC machining.
  plate/plate/face 3: internal corner radius 0.5 mm is under the 1.5 mm minimum (8 mm tall, a corner of the cavity at plate/plate/face 14)
  ...
info: material_declared at bodies: material aluminum, read from the part's declared material (Alu_G6061_T6): give --material to judge another
FAILED 6c29e879-9e27-55ce-9cc9-1863a83e2a95: 4 error(s), 4 warning(s); cnc 3-axis milling: 1 part(s), 48001.7 mm3, 1 setup(s), 1 pockets; failed: cnc.internal_corner_radius x4
```

A failing rule is said once, with its hint and its source, then a line for each feature at its ref;
any other finding is one line. The last line is the check's state, and so is the exit status:

| Last line | Exit | `status` | It says |
| --- | --- | --- | --- |
| `OK <id>: [N warning(s); ]<what was measured>` | 0 | `ok` | every part was measured and no finding is an error. Not an approval: warnings (recommendations, cost, risk) and rules not evaluated remain |
| `FAILED <id>: E error(s)[, W warning(s)]; <what was measured>; failed: <code> xN, ...` | 1 | `failed` | a finding is an error: the part cannot be made by this process as drawn. With `--strict`, a warning fails too |
| `NOT CHECKED <id>: <code> ...` | 3 | `not_checked` | the check did not judge what it was asked to: never a pass, never "no findings" |

Exit 2 (`"status": "usage"`) is the command refused. Its message says the fix, which is in the
command, not the part.

`--json` prints the result as one line: `status`, `ok` (true for `ok` alone), `reason`, `summary`,
`findings` and `measurements`. Key on `status` or the exit, never on a finding's severity: a
`NOT CHECKED` result carries an `error` finding too, the one whose code is its `reason`, which says
why nothing was judged, not that the part fails.

- **Not checked.** The `reason` is of three kinds, and its finding says what to do. Nothing to
  measure: no closed solid (`not_solid`: an open shell, a face), or a source that does not read or
  holds nothing (`document_unreadable`, `document_empty`, a mesh's `mesh_unreadable` and
  `mesh_empty`, a cut file's `no_cut_geometry`). Part of it not judged, the rest still reported: a
  family (`measurement_failed`), faces the kernel failed on (`rays_unintersected`), features a rule
  had no figure for (`rule_partly_judged`: its `refs`), or no rule with a limit here
  (`rules_none_evaluated`). Or the check did not run to its end: past half an hour or its memory
  limit (`over_time`, `over_memory`: check a smaller part, or raise the limit the message names),
  the server stopped, or the model built again under it (`superseded`): run it again. A check the server stopped has no findings: `--json`
  is `{"ok": false, "error": ..., "reason": ..., "status": "not_checked"}`, and stderr says
  `NOT CHECKED (<reason>)` and why. A part that fails and was not wholly checked is `FAILED`, its
  line ending `; not checked: <code> xN`.
- **One count.** The line's errors and warnings count features, one finding each, and
  `failed: <code> xN` is the same count by rule. Past eight features of one rule the text says
  `and N more`, and `--json` has one more finding that lists them.
- **Order.** What puts every figure in doubt comes first, whatever its severity: what was not
  checked, `not_watertight` and `not_sound` (errors in every process) and `units_suspect` (a part
  under 1 mm or over 10 m across, probably in the wrong unit: its note names the readings that
  fit). Then errors, warnings and facts.
- **A rule's finding is data.** In `--json` its code is the rule's id (`rule`), and it carries
  `value`, `limit`, `unit`, `op` (`min`: at least; `max`: at most), `source` and `refs`: every ref
  of the feature, the most specific first (a corner's edge, then its faces), `location` being the
  first. Edit from those, never from the message. Several failures of a rule at one feature are one
  finding (`and 2 more at this ref`), and a recommendation on a figure that already fails a stricter
  rule there is left to `measurements.rules`.
- **Whose limit.** A limit no published guide states is text-to-cad's own floor, and its `source`
  says so (`cad, its own figure: ...`): report it as that, never as a guide's.
- **Facts.** A code that is no rule's is a fact or an assumption the figures call for:
  `process_declared` and `material_declared` (read from the part), an option the check assumed
  (`cnc.material_assumed`, `resin_unknown`, `sheet.k_factor_assumed`: report it), `several_solids`
  (a warning: one part of several solids, its message saying how the process read them) and
  `several_bodies` (several parts, every occurrence counted).
- **The place and the figures.** Resolve a ref with `cad model inspect "$ID" '<ref>'`, a file's
  with `cad step inspect part.step '<ref>'`. The figures behind a finding are
  `measurements.<family>.items`, worst first.
- **What was not judged.** `measurements.rules.outcomes` has one entry for every rule, failed or
  not: `rule`, `status`, `limit` (for this part's options), `source`, `reason` and `failures`, each
  with its `refs`, its `xyz` and the index of its `item` in its family. `measurements.rules.sources`
  has each guide's URL. By `status`:

  | `status` | Report it as |
  | --- | --- |
  | `passed` | a pass; with the reason "none found" (`rules.none_found`) it had nothing of its kind to judge: say none was found |
  | `failed` | a failure, an error (not made as drawn under that rule) or a warning (a recommendation) |
  | `partial` | a pass of the features it judged alone: `rule_partly_judged` names the rest, and the check is `NOT CHECKED` |
  | `not_evaluated` | unverified, never a pass: the rules give no limit here, or the figure was not measured |
  | `not_applicable` | nothing: the rule is for another context (another technology, turning) |

  What a source does not hold is said once (`families_not_measured`, info): a mesh's pins and
  details, a cut file's bends, reliefs, hems and thickness. Check the STEP, the model or the bent
  part for those rules.

## The review

The check is evidence, not a certification: it measures what its families cover and judges what its
rules have numbers for. A review says:

- **the scope**: the file and revision, the parts, the process, the material, the units, and what
  the check was told of the shop or assumed;
- **the findings**: each feature at its ref with the measured value, the rule with its limit and
  source, the result, and a specific change (the hint, with this part's numbers). An error is a
  constraint; a warning is a recommendation, a cost or a risk: keep the two apart;
- **the coverage**: the rules not evaluated, the rule table's `note` (`measurements.rules.note`) and
  the process reference's checks by hand.

A result is a pass, a failure, a review item (a risk from the checks by hand) or unverified: a rule
not evaluated, the features a `partial` rule left, a family not measured, anything a `NOT CHECKED`
result did not reach, a check by hand without the evidence. Report no value that was not measured.

## Check a redesign

A review asks for no edit, upload or order. For a redesign, edit the model's source, run it, and run
the same check with the same options on the new revision. The finding's code should be gone from its
place and no new one appear beside it (a moved hole can open one): compare
`measurements.rules.failed` before and after, and each outcome's `failures` by `xyz`, since face and
edge numbers change with an edit. Check the file the shop takes once it is exported, never the model
alone.
