# Burr design-rule loop

Use this reference when `$cad-burr` is active. The goal is not to make CAD
generation more complicated; the goal is to make agent claims traceable to
machine-readable checks.

## What Burr checks

Burr checks declared design metadata against a rulepack. Typical metadata
describes feature intent, dimensions, source hashes, artifact hashes, holes,
bosses, insert pockets, slots, bearing seats, counterbores, spacing envelopes,
and feature-pair rules.

Burr does not infer every feature from a screenshot, and it does not make
unbounded manufacturing claims. If the CAD source does not emit metadata for a
feature, Burr may have nothing meaningful to check for that feature.

## Source expectations

Prefer build123d source that uses normal CAD operations for geometry and
`burr_build123d` helpers for metadata. Keep the metadata close to the source
parameters that create the geometry.

Useful install checks:

```bash
burr --version
python -c "import burr_build123d"
```

Typical project installs:

```bash
cargo install burr
uv add burr-build123d
```

For build123d projects, use:

```python
from burr_build123d import BurrDesignData
```

Use specialized helpers such as clearance-hole, boss, insert-pocket, slot,
bearing-seat, counterbore, or spacing-envelope helpers when they match the
feature being created. Use plain metadata declarations for features that do not
fit a helper yet.

## Check loop

Create real source and artifacts before checking them:

1. Create or repair build123d source.
2. Generate the STEP artifact from explicit source targets.
3. Run geometry inspection and snapshot review.
4. Run Burr against the emitted design data and rulepack.

Rulepack selection is mandatory. Put a built-in selector or `rulepack.path` in
the design data, or pass `--rulepack <selector>` explicitly. Burr never chooses
a default rulepack silently. Common command shapes are:

```bash
burr check path/to/project-or-design-data
burr check --rulepack path/to/rulepack.json path/to/project-or-design-data
```

Treat the written Burr receipt as an artifact. Keep its path in the final
answer when the user needs proof. Inspect `schema_version` and `outcome` in the
receipt: current receipts use `burr.receipt.v2`, with `pass`, `incomplete`, or
`fail`. The CLI exits `0`, `3`, or `1` for those outcomes respectively and `2`
for invocation or configuration errors that prevent a receipt-backed run.

## Repair loop

When Burr returns `fail` or a repairable `incomplete` outcome:

1. Read the Burr receipt.
2. Run:

   ```bash
   burr explain --json path/to/burr-repair-report-or-receipt.json
   ```

3. Prefer exact source hints when present.
4. Edit the smallest responsible build123d source section.
5. Regenerate STEP and design data.
6. Rerun geometry and snapshot validation that could be affected by the edit.
7. Rerun `burr check`.

For `fail`, repair the checked design-rule violation or invalid contract. For
`incomplete`, repair the missing compatibility, evaluated-rule coverage, or
required mechanical-feature coverage. `burr explain --json` emits a structured
`burr.repair-packet.v2` packet that preserves both failure and incomplete
reasons.

Do not edit generated STEP, STL, GLB, topology, or receipt files as the fix.
Repair the source that emits the geometry and metadata.

## Decision rules

Return `passed` only when:

- STEP generation succeeded.
- Required geometry inspection and snapshot checks ran or a documented skip
  case applies.
- Burr returned a `burr.receipt.v2` receipt with `outcome: pass` for the intended
  rulepack, at least one evaluated rule, and complete required mechanical
  coverage.

Return `need_user` when an `incomplete` outcome or missing requirements block an
honest repair, such as unknown fit target, unknown material/process, missing
component envelope, uncovered mechanical intent, or conflicting design intent.

Return `failed` when tooling cannot generate, inspect, or check the artifact in
the current environment, or when repair attempts would be speculative.

## Reporting

Report:

- source file path
- generated STEP/STP path
- Burr design data path
- Burr receipt path
- rulepack path
- receipt outcome, scope warnings, and checks that passed or failed
- repair actions applied, if any
- preview links and snapshots, when produced
- remaining caveats

Use direct language. Do not say "printable", "manufacturable", "safe", or
"verified" without saying exactly which checks support that claim.
