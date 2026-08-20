# Label selector refs: `#servo_end_plate.f45`

Implementation plan. Written for direct execution — every file path, algorithm, and
verification command is stated; do not re-derive them. Measured facts below were taken
from develop @ `2858d985` (post-0.4.15).

## Goal

Let users reference occurrences by their build123d label instead of the numeric
occurrence id, everywhere a selector ref is *accepted* today:

```
#eye_shank              same part as  #o1.1.2
#eye_shank.f45          same face as  #o1.1.2.f45
#servo_end_mount_2      second of two occurrences labelled servo_end_mount
```

## Locked decisions (do not relitigate)

1. **Accept, don't emit.** Tools resolve label refs as input. Copy buttons, snapshot
   JSON `ref` fields, and error messages keep emitting numeric refs. Emission is a
   separate future decision.
2. **Duplicate labels are allowed** and stay allowed. When N>1 occurrences share a
   label, each gets a numbered alias `<label>_1` … `<label>_N` in deterministic tree
   order. The bare duplicated label resolves to nothing and errors listing the
   numbered candidates. Unique labels resolve bare (no number needed or accepted).
3. **Labels are surface syntax; numerics are the wire format.** Label refs are
   resolved to numeric canonical form at the index layer, *before* crossing any
   boundary: Python→JS render jobs, saved files, emitted JSON. No renderer,
   topology, or geometry code learns about labels.
4. Grammar keeps its existing behavior for everything else: unknown selectors still
   fall through to `opaque` (no new hard failures at parse time). Resolution — not
   parsing — is where a bad label errors.

## Measured ground truth

- Occurrence rows already carry `name` from the build123d `.label`
  (`packages/cadgen/src/cadgen/instances.py:81`); `snapshot --mode list` emits it
  (`{"ref":"#o1.1.2","name":"eye_shank"}`). No generator-side plumbing needed.
- Label charset in the wild (156 labels, 3 assemblies): alphanumerics plus `:` and
  `_` only. Zero contain `.`; zero match `^o\d`; `:` appears mid-label
  (`mounting_eye:lower`, `piston_rod:chrome`, `cast_rim:5spoke`).
- Duplication is real and legitimate: motorbike = 46 parts, 41 distinct labels
  (`cast_rim:5spoke` ×2, `turn_signal_housing:left` ×2, …). Shock absorber,
  planetary gear, six-axis arm: fully unique.
- The grammar exists in FOUR places with no parity test:
  1. `packages/cadgen/src/cadgen/cad_ref_syntax.py` (canonical, 3 regexes)
  2. `packages/cadjs/src/lib/cadRefs.js` (same 3 regexes)
  3. `viewer/src/client/components/CadWorkspace.js:429` (`NATIVE_CAD_SELECTOR_RE`,
     also accepts `m\d+`)
  4. `viewer/src/client/workbench/referenceSelection.js:263` (byte-identical inline
     copy of 3 — and this file already imports cadRefs.js)
- `SelectorIndex` (`packages/cadgen/src/cadgen/lookup.py:57`) is a frozen dataclass
  with `occurrence_by_id` etc. There are exactly TWO index construction sites, both
  ending in `index_with_assembly_occurrences(index, artifact)`:
  `snapshot_cli.artifact_selector_index` and
  `skills/cad/scripts/inspect/inspect_refs/inspect.py:255`.
- Snapshot focus/hide selectors are validated python-side in
  `packages/cadgen/src/cadgen/snapshot_core.py` (selection normalization ~lines
  605–640, `SELECTION_SHAPED_JOB_KEYS`). That is the choke point where labels must
  become numerics before the JS render job is built.
- `parse_selector` today returns `opaque` for `m1` (mates) — mate handling lives in
  consumers. A naive label regex would swallow `m\d+`; it must not.

## Phase 0 — consolidate the grammar copies (prerequisite, standalone PR)

Do this first regardless; it is the safety net for every later phase.

1. In `packages/cadjs/src/lib/cadRefs.js`, export `isNativeCadSelector(candidate)`
   implementing the union regex (occurrence | occurrence.entity | entity | `m\d+`).
2. Replace the inline regex at `CadWorkspace.js:429` and
   `referenceSelection.js:263` with that import (referenceSelection already imports
   the module).
3. Add a shared parity fixture `packages/cadjs/src/lib/cadRefs.parity.json`: an
   array of `{selector, type, occurrenceId, ordinal, canonical}` cases covering
   every grammar form, including the future label forms marked `"phase": 1` so both
   suites skip-then-enable them. Root Python test
   `tests/python/packages/cadgen/test_cad_ref_syntax_parity.py` loads the fixture
   (root tests may reach into `packages/`); `cadRefs.test.js` loads it relatively.
   Both assert their parser agrees with every case.

Checks: `npm --prefix packages/cadjs test`, `npm --prefix viewer run test`,
`./.venv/bin/python -m unittest tests/python/packages/cadgen/test_cad_ref_syntax_parity.py`.

## Phase 1 — grammar: parse label forms (Python + JS)

`cad_ref_syntax.py` and `cadRefs.js`, kept in lockstep via the parity fixture.

New regexes (tight on purpose — widening later is compatible, narrowing is not):

```
LABEL        = [A-Za-z_][A-Za-z0-9_:]*
LABEL_SELECTOR_RE        = ^(LABEL)$
LABEL_ENTITY_SELECTOR_RE = ^(LABEL)\.([sfev])(\d+)$
```

Parse order in `parse_selector` (and the JS mirror): occurrence-entity, occurrence,
entity — all unchanged — THEN label forms, THEN opaque. Guards before the label
branch returns:

- if the selector matches `^m\d+$` → opaque (mates keep today's path);
- (`f45`, `o1` can never reach the label branch — earlier regexes claim them).

`ParsedSelector` gains `selector_type` values `"label"` and (entity case) the
existing `face/edge/vertex/shape` types with a new field `label: str = ""` set when
the occurrence was named by label. `canonical` for label forms keeps the label
spelling (`eye_shank.f45`) — canonicalization to numerics is resolution's job, not
the parser's.

Comma-list inheritance (`normalize_selector_list`): after a label selector, a bare
`f46` inherits the *label* the same way it inherits an occurrence id today —
canonical becomes `eye_shank.f46`. Track `inherited_label` alongside
`inherited_occurrence_id`; occurrence wins if both somehow appear.

Enable the `"phase": 1` fixture cases in both suites.

## Phase 2 — alias map + resolution (Python, cadgen)

New module `packages/cadgen/src/cadgen/label_refs.py`. Small, pure, no I/O.

### Alias algorithm (deterministic; implement exactly)

Input: the index's occurrence rows (leaf AND group rows — modules like
`damper_body` are addressable too). Output: `dict[str, str]` alias → occurrence id.

```
1. order rows by occurrence id, sorted on the numeric path components
   (o1.2 < o1.10; NOT lexicographic).
2. sanitize each row's name: if it does not fully match LABEL, or matches
   ^m\d+$ / ^[sfev]\d+$ / ^o\d, the row gets NO bare alias (it is only
   reachable numerically); record it in a `skipped` list for diagnostics.
3. group rows by sanitized name.
   - group of 1  -> alias  name        -> that occurrence id
   - group of N  -> aliases name_1..name_N in the order from step 1;
                    the bare name maps to the sentinel AMBIGUOUS with the
                    candidate alias list attached.
4. collision rule: numbered aliases are chosen as the smallest k >= 1 such
   that name_k is not an AUTHORED name of any other row and not already
   assigned. (Protects against an author literally labelling one part
   servo_end_mount and another servo_end_mount_1.)
```

Attach the result to the index. `SelectorIndex` is frozen — add a field
`label_aliases: dict[str, object]` (default empty) and populate it in a helper
`attach_label_aliases(index)` applied at BOTH construction sites, after
`index_with_assembly_occurrences` (assembly merge changes the row set, so aliases
must be computed on the merged rows):

- `packages/cadgen/src/cadgen/snapshot_cli.py` — `artifact_selector_index` tail
- `skills/cad/scripts/inspect/inspect_refs/inspect.py:255`

### Resolution

`label_refs.resolve_label_selectors(selectors, index) -> list[str]`: map each
canonical label form to numeric canonical (`eye_shank.f45` → `o1.1.2.f45`), pass
numeric/opaque selectors through untouched. Errors are `SnapshotError`-compatible
messages:

- unknown label → `unknown label 'X'; run snapshot --mode list to see part names`
- ambiguous bare label → `label 'cast_rim:5spoke' matches 2 occurrences; use
  #cast_rim:5spoke_1 (o1.3.2) or #cast_rim:5spoke_2 (o1.7.2)`

Call it at the existing python-side selector choke points so the wire format stays
numeric (decision 3):

- snapshot: selection normalization in `snapshot_core.py` (~605–640) for
  focus/hide/refs, before job build
- inspect refs: where parsed selectors are looked up against the index

### Discoverability (read-only, allowed under decision 1)

`inspect` refs rows and `snapshot --mode list` parts gain one field:
`"labelRef": "#eye_shank"` / `"#cast_rim:5spoke_2"` (omit for rows with no alias).
This is new JSON output, not a change to any existing field — existing consumers
keep working. It is how users learn the alias spelling without guessing.

## Phase 3 — viewer accepts pasted label refs

Scope: the paste/typed-ref surfaces only (`referenceSelection.js` candidate
acceptance and whatever `CadWorkspace` feeds it). The viewer holds the parts list
client-side with names per ref, so:

1. `cadRefs.js` gains `buildLabelAliasMap(parts)` implementing the SAME algorithm
   (add algorithm cases to the parity fixture: given a parts array, expected alias
   map — both languages assert it).
2. `referenceSelection.js` resolves label candidates through that map before its
   existing numeric path. Ambiguous/unknown labels are rejected as a candidate
   (same as any invalid ref today) — viewer UX for error toasts is out of scope.

## Out of scope (explicitly)

- Emitting label refs anywhere (copy buttons, snapshot output, error text).
- Hierarchical label paths (`#rear_wheel/cast_rim`).
- Renaming/uniquifying labels at generation time, or forbidding duplicates.
- Mate labels (`m1` stays opaque/numeric).
- `.params.js` sidecar refs and any JS render-runtime selector handling — those
  receive numerics by decision 3 and must not change. If implementation finds a
  spot where a raw user selector crosses to JS unresolved, resolve it python-side
  at that spot rather than teaching JS the labels.

## Gotchas for the executor

- **Vendored runtimes:** skills bundle cadgen (`skills/cad/scripts/packages/cadgen`)
  and the snapshot JS runtime bundles cadjs. After source edits run
  `scripts/bundle/bundle.sh`, verify with `scripts/bundle/bundle.sh --check`, and
  restore the dev symlink layout (`scripts/dev/setup-symlinks.sh`) if continuing on
  develop. Editing only `packages/` without rebundling makes skill tests pass
  locally against stale copies.
- **Frozen dataclass:** `SelectorIndex` field addition must default (`field(default_factory=dict)`)
  so `dataclasses.replace` call sites elsewhere keep working.
- **Two construction sites, not one.** Missing `inspect.py:255` reproduces the
  exact class of bug fixed in PR #277.
- **Do not** loosen the LABEL charset to include `.` or leading digits — `.` is the
  entity separator and `^o\d`/`^[sfev]\d` are claimed. Enforcement is at alias
  build (step 2 skip), not at generation.
- Windows CI runs the same suites automatically; no extra wiring needed.

## Test matrix

Python (`tests/python/packages/cadgen/`):
- `test_cad_ref_syntax_parity.py` — fixture-driven, both grammars (Phase 0/1).
- `test_label_refs.py` — alias builder: unique bare, duplicate numbering order
  (numeric path order, o1.10 after o1.2), collision-with-authored-name rule,
  skipped charset rows, group rows aliased, ambiguous sentinel; resolution: happy
  path, entity suffix, comma inheritance, unknown error text, ambiguous error text
  lists numbered candidates with occurrence ids.
- Integration in the existing suites: snapshot `--focus '#eye_shank'` on the shock
  absorber fixture selects the same rows as `--focus '#o1.1.2'`; motorbike
  `#cast_rim:5spoke` errors with both candidates; `#cast_rim:5spoke_2.f3`
  resolves; `--mode list` rows carry `labelRef`.

JS:
- `cadRefs.test.js` — parity fixture + `buildLabelAliasMap` fixture cases.
- viewer test for `referenceSelection` accepting a label candidate against a
  stubbed parts list.

## Verification commands

```
./.venv/bin/python -m unittest tests/python/packages/cadgen/test_cad_ref_syntax_parity.py tests/python/packages/cadgen/test_label_refs.py
scripts/test/test-python.sh
npm --prefix packages/cadjs test
npm --prefix viewer run test
scripts/bundle/bundle.sh --check
```

## Acceptance criteria

1. `snapshot --focus '#eye_shank' -i models/step/assemblies/motorcycle_shock_absorber.step.py`
   renders identically to the numeric ref (same selected occurrence ids in the job).
2. Motorbike duplicate labels behave exactly per decision 2 (bare errors listing
   `_1`/`_2`; numbered forms resolve; order follows the occurrence tree).
3. Every numeric ref that worked before still works byte-for-byte; no emitted
   `ref` field anywhere changes.
4. Parity fixture green in both languages; the two inline viewer regexes are gone.
5. Full `scripts/test/test-python.sh` and both JS suites green; bundle check clean.
