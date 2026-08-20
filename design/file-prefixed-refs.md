# File-prefixed refs: `mounting_plate.stl#o1.2.f3`

Implementation plan, written for direct execution — file paths, algorithm, guard
semantics, and verification commands are stated; do not re-derive them. Measured
facts below were taken on develop @ 0.4.17 (post-#285/#287).

## Goal

A ref copied from the viewer should say which file it belongs to, compactly, so it
stays meaningful when pasted into a prompt that spans several files:

```
motorcycle_shock_absorber.step.py#o1.1.2      one file in the whole tree has this name
starship/super_heavy.step.py#o1.3             two files are named super_heavy.step.py;
                                              one directory segment disambiguates
```

## Locked decisions (do not relitigate)

1. **The prefix is the Shortest Unique File Path suffix (SUFP)**: the fewest
   trailing path segments (filename included, extension included) that name
   exactly one catalog entry. No hash pinning — rejected after design review.
2. **The viewer emits, the agent splits.** Copy buttons prefix refs with the
   SUFP. The AGENT (Claude/Codex following the CAD skill docs) splits at `#`,
   resolves the SUFP to a real path by suffix-matching project files, and passes
   file and `#ref` to the CLIs as separate arguments — exactly as today.
3. **CLIs stay file-local.** No CLI resolves a SUFP to a file. The only CLI
   change is a guard: a ref that carries a prefix matching the CLI's own entry
   target is stripped and accepted; a prefix naming a DIFFERENT file is a hard
   error telling the agent to split. Never silently ignored — see the trap below.
4. `.step.py` stays in the prefix. CLIs accept `.step.py` targets directly, so
   the agent's resolution is a literal suffix match with no normalization step.
5. Bare `#ref` remains valid everywhere, emitted and accepted, byte-identical in
   behavior. This is additive.

## Measured ground truth

- Filename+extension is almost always enough: of 404 model files, only **3
  filenames collide** (`super_heavy.step.py` ×2, `sts3250.step` ×2,
  `link_assembly.step.py` ×2). (Bare stems collide badly — 71 of 315 — because
  of format siblings like `mounting_plate.{step.py,stl,3mf,glb}`; the extension
  is their discriminator, which is why SUFP keeps it.) So SUFP = filename for
  ~99% of entries and one directory segment for the rest.
- **The grammar already reserved the slot.** `ParsedToken.cad_path` exists and
  is filled with `""` (`packages/cadgen/src/cadgen/cad_ref_syntax.py`,
  `parse_cad_tokens`); `build_cad_token(cad_path, selector)` takes a path and
  DISCARDS it (`_ = cad_path`); `CAD_TOKEN_RE = ^\s*#([^\s]*)` captures only
  after `#`. The JS mirror (`packages/cadjs/src/lib/cadRefs.js`,
  `parseCadRefToken`) returns `cadPath: ""`. This plan fills the slot.
- `canonicalCadRefCopyText` requires `startsWith("#")`
  (`viewer/src/client/workbench/referenceSelection.js:251`) — prefixed copy text
  fails it today, so the token layer must learn the prefix BEFORE emission
  changes, or copy-button labels break.
- Copy builders already receive the entry:
  `buildAssemblyPartCopyText(part, entry)` (:295),
  `buildWholeStepEntryCopyReference(entry)` (:316),
  `buildAssemblyMateCopyText(mate, entry)` (:330),
  `buildSelectionCopyPayload({..., entry})` (:339), all in
  `viewer/src/client/workbench/referenceSelection.js`. The full entries array
  lives where the sidebar/asset state is built (`viewer/src/client/workbench/
  sidebar.js` consumers, `useCadAssets`).
- The in-app example string ("Make the hole #o1.1 twice as wide") lives in
  `viewer/src/client/components/workbench/TutorialTip.jsx`.
- The docs sentence this feature obsoletes: "Selector refs are local to the
  STEP/CAD entry target passed to the command. They do not include file paths"
  — `skills/cad/references/inspection-and-validation.md:31`.
- Parity fixture: `packages/cadjs/src/lib/cadRefs.parity.json` currently has
  `selectorCases` / `inheritanceCases` / `aliasCases`, asserted by BOTH
  `tests/python/packages/cadgen/test_cad_ref_syntax_parity.py` and
  `packages/cadjs/src/lib/cadRefs.test.js`. Token parsing gets `tokenCases`
  there, same both-languages discipline.

## THE TRAP (read before phase 3)

`_parse_entry_ref_tokens` in `skills/cad/scripts/inspect/inspect_refs/inspect.py`
re-builds every parsed token with `cad_path=<the CLI's entry argument>` —
overwriting whatever the grammar parsed. Once the grammar starts capturing
prefixes, that overwrite becomes: *user passes a ref for file A while the command
targets file B, and the tool silently inspects B.* That is the same
silent-wrong-answer class as the `validate --refs <label>` zero-occurrence bug
fixed in #285. The guard in phase 3 exists to close it; do not skip it, and do
not implement it as "ignore the prefix".

## SUFP algorithm (exact; JS only)

Python never computes a SUFP — agents resolve by matching, CLIs only compare
against their own target. One implementation, in `packages/cadjs/src/lib/`:

```
shortestUniquePathSuffix(paths):
  input: every catalog entry's file path (POSIX, relative to the served root)
  for each path P (segments = P.split("/")):
    for k = 1 .. segments.length:
      candidate = last k segments joined with "/"
      if no OTHER path shares its last k segments -> SUFP(P) = candidate; break
  returns Map(path -> suffix)
```

Deterministic given the path set. Recomputed whenever the catalog changes;
adding a colliding file lengthens the SUFP of an existing entry (accepted —
acceptance of longer spellings is what stays stable, per the design decision
that emission may drift while acceptance never breaks).

## Phase 0 — token grammar learns the optional prefix (Python + JS)

`cad_ref_syntax.py` and `cadRefs.js`, in lockstep via new `tokenCases` in the
parity fixture.

- `CAD_TOKEN_RE` becomes `^\s*([^#\s]*)#([^\s]*)` — group 1 (possibly empty) is
  the raw prefix, group 2 the selector list. Bare `#o1.2`, bare `#`, and
  prefixed `mounting_plate.stl#o1.2,f3` all match; `parse_cad_tokens` /
  `parseCadRefToken` fill `cad_path` / `cadPath` with the RAW prefix (no
  normalization — see locked decision 4).
- `build_cad_token(cad_path, selector)` / `buildCadRefToken({cadPath, ...})`
  stop discarding the path: emit `${cadPath}#${selectors}` when given, `#...`
  otherwise. Note `<sufp>#` (empty selector list) is now a meaningful token:
  "this whole file".
- `canonicalCadRefCopyText` accepts prefixed tokens (route through the updated
  token parser instead of the `startsWith("#")` test), as does
  `canonicalCopyTextForSelector` in `CadWorkspace.js`.
- Fixture `tokenCases`: bare selector token, bare whole-entry `#`, prefixed
  single, prefixed comma-list (inheritance still applies within the token),
  prefixed whole-entry, junk without `#` (not a token).

Selector-level grammar (`parse_selector`) is UNTOUCHED — the prefix lives at the
token layer, left of `#`, which is why it cannot collide with labels, `:`, or
entity dots.

## Phase 1 — `shortestUniquePathSuffix` helper + tests (cadjs)

Pure function as specced above, beside `cadRefs.js`. Tests pin: filename-unique
case; the real collision pairs (`super_heavy.step.py` twins resolving to
one-directory-qualified suffixes); three-way collisions; recomputation when a
colliding path is added; empty and single-element inputs. Segment-aligned comparison only
— `late.stl` must NOT be a suffix of `mounting_plate.stl` (compare whole
segments, never substrings).

## Phase 2 — viewer emits SUFP-prefixed copy text

- Compute the map once where the entries array is assembled (sidebar/useCadAssets
  state), attach as `entry.fileRefPrefix`. Entries lacking the field emit bare
  `#...` — that keeps every existing unit test that builds minimal entry objects
  passing, and makes the change opt-in per call site.
- Thread through the four copy builders listed above via the `entry` they
  already receive: `buildCadRefToken({cadPath: entry.fileRefPrefix, ...})`.
  Copy-button labels pick the prefix up automatically ("Copy
  motorcycle_shock_absorber.step.py#o1.1.2").
- Paste round-trip: in the candidate-acceptance path (`resolveViewerSelector`
  and callers), a pasted token whose prefix segment-matches the CURRENT entry's
  file path is stripped and processed as today; a prefix naming a different
  entry is rejected as a candidate (same handling as any unusable selector).
  Cross-file navigation-on-paste is explicitly out of scope.
- Update the `TutorialTip.jsx` example to the prefixed form so the first thing
  users see matches what Copy produces.

Intended behavior change, stated plainly: copy text gains a prefix. Tests that
assert exact copy text must be updated WITH entry fixtures carrying
`fileRefPrefix`, not by weakening assertions.

## Phase 3 — CLI guard rails (Python)

At the two places raw user ref strings first become tokens/selectors:

- `inspect.py` `_parse_entry_ref_tokens`: when the parsed token's `cad_path` is
  non-empty — if it segment-suffix-matches the command's entry target (equal, or
  target endswith `/<prefix>`), strip it and continue; otherwise raise
  `CadRefError`:
  `ref 'X#o1.2' names file 'X' but this command targets 'Y'; pass the file as
  the entry argument and '#o1.2' as the ref (see references docs)`.
- `snapshot_cli.py` `normalize_selection_selector`: same rule against the
  render `--input` path, raising `SnapshotError` with the same wording.
- Audit `run_measure` / `run_align` / `run_frame` / `run_validate` /
  `run_interfere` in `inspect_refs/cli.py` for any ref string that reaches
  `parse_selector` WITHOUT passing one of the two guarded points, and route or
  guard it. Cite: #285's validate/interfere bug came from exactly such a third
  path (`interference._selected`). A raw selector containing `#` mid-string or
  `/` today falls to `opaque` — after this phase it must never silently do so
  when it carries a prefix.

## Phase 4 — skill docs (the agent contract)

- `skills/cad/references/inspection-and-validation.md`: rewrite line 31's
  paragraph. New subsection **"File-prefixed refs (viewer copy format)"**:
  - format: `<shortest-unique-path-suffix>#<refs>`; the suffix always includes
    the filename with extension and may include trailing directories.
  - agent workflow, verbatim steps: split at the first `#`; resolve the prefix
    by suffix-matching project files (e.g. `git ls-files '*<name>'` or a glob),
    segment-aligned; pass the resolved file as the entry/input argument and
    `#<refs>` as the ref argument, exactly as before.
  - note: CLIs strip a matching prefix but ERROR on a mismatched one — they
    never resolve prefixes themselves.
- `skills/cad-viewer/references/viewer-features.md`: one short paragraph on the
  copy format next to the existing Measure/copy feature notes.

## Out of scope

- CLI-side SUFP→path resolution (the agent owns resolution).
- Cross-file paste navigation in the viewer.
- Hash pinning (`@stepHash`) — rejected in design review.
- Emitting label refs from copy buttons (still numeric; prefix composes with
  whatever the selector side emits).
- Mesh/DXF copy surfaces (meshes have no ref copy today; nothing to prefix).

## Gotchas for the executor

- **Bundle discipline**: cadjs and cadgen edits require
  `scripts/bundle/bundle.sh`, then `scripts/bundle/bundle.sh --check`, then
  `scripts/dev/setup-symlinks.sh` to restore the dev layout before committing.
- The parity JSON must stay test-only — imported by the two test suites, never
  by runtime code, or it ships in the cadjs bundle.
- Both token regexes change in lockstep; the parity `tokenCases` are the only
  thing keeping them honest. Add cases FIRST (phase 0), watch them fail, then
  implement.
- Segment-aligned matching everywhere (`/`-boundary), never substring.
- Do not normalize the prefix through `normalize_cad_path` — it strips
  `.step.py`, which would break the agent's literal suffix-match contract.
- Windows CI runs the same suites automatically; nothing extra to wire.

## Test matrix

- Python: parity `tokenCases`; inspect guard (matching prefix stripped —
  equal and dir-qualified forms; mismatched prefix errors naming both files;
  bare refs untouched); snapshot guard (same three).
- JS: parity `tokenCases`; `shortestUniquePathSuffix` unit tests per phase 1;
  copy builders with/without `fileRefPrefix`; `canonicalCadRefCopyText` on
  prefixed text; paste round-trip accept/strip/reject in referenceSelection.
- Integration: on the real catalog, `motorcycle_shock_absorber.step.py` gets a
  bare-filename SUFP and the `super_heavy.step.py` pair get directory-qualified
  ones (assert via the helper against the scanned models tree, or a fixture
  mirroring it).

## Verification commands

```
./.venv/bin/python -m unittest tests/python/packages/cadgen/test_cad_ref_syntax_parity.py
scripts/test/test-python.sh
npm --prefix packages/cadjs test
npm --prefix viewer run test
scripts/bundle/bundle.sh --check
```

## Acceptance criteria

1. Copying a part on the shock absorber yields
   `motorcycle_shock_absorber.step.py#o1.1.2` (filename-unique SUFP), and a
   `super_heavy.step.py` entry yields a directory-qualified prefix.
2. Pasting the copied text back into the viewer on the same file selects the
   same part; pasting it on a different file rejects it rather than mis-selecting.
3. `inspect refs <entry> '<matching-sufp>#o1.1.2'` behaves identically to the
   bare ref; a mismatched prefix errors naming both files, on inspect AND
   snapshot paths. No code path silently drops a prefix.
4. Every bare `#ref` behaves byte-identically to before, emitted and accepted.
5. Docs updated per phase 4; full Python + cadjs + viewer suites green;
   `bundle.sh --check` clean with the dev symlink layout restored.
