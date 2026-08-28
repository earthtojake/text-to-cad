---
name: burr
description: Burr-verified CAD generation loop. Use when the user wants STEP-first parametric CAD that emits Burr design metadata, runs explicit design-rule checks, repairs source from Burr receipts, and only claims confidence from checks that actually passed.
---

# Burr generation and repair loop

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Purpose

Create or modify STEP-first parametric CAD with Burr design-rule feedback in the
loop. This skill owns the minimal build123d generation, artifact inspection, and
Burr workflow it requires; it does not depend on sibling skills at runtime. It
adds a mandatory Burr pass/incomplete/fail/repair loop around source-driven CAD
generation.

Burr checks declared design intent and metadata. It does not replace geometry
inspection, snapshot review, interactive preview review, manufacturing process
review, tolerance analysis, FEA, or fabrication testing.

## Use this skill when

Use this skill when the user asks for Burr-verified CAD, design-rule checked
CAD, CAD with machine-readable repair receipts, or an agent loop that should
catch declared mechanical/design-rule mistakes before handing off the artifact.

Use an ordinary CAD workflow when the user does not want Burr metadata or
design-rule enforcement. Fabrication, slicing, and printer handoffs remain
separate downstream work after the checked CAD artifact exists.

## Required tools

Before claiming Burr verification, confirm the required Burr tooling is
available in the active environment:

```bash
burr --version
python -c "import burr_build123d"
```

If the tools are missing, install them only when the user or workspace policy
allows dependency installation. Typical installs are:

```bash
cargo install burr
uv add burr-build123d
```

If Burr cannot be installed or run, stop and report the blocker. Do not silently
fall back to an unchecked CAD workflow while still calling the result
Burr-verified.

## Required workflow

Load `references/burr-design-rule-loop.md`. The Burr loop is mandatory inside
this skill:

1. Convert the request into an explicit CAD brief and parametric plan.
2. Author or modify build123d source so it emits Burr design data alongside the
   STEP artifact.
3. Generate the STEP from explicit source targets.
4. Inspect the generated geometry and review representative snapshots.
5. Run `burr check` with an explicit rulepack selected in the design data or by
   `--rulepack <selector>`.
6. Read the receipt `outcome`. Treat `incomplete` as a blocked trust claim, not
   as a weaker pass.
7. For `fail` or repairable `incomplete`, run `burr explain --json`, repair the
   smallest responsible source section, regenerate, repeat affected geometry
   validation, and rerun Burr.
8. Stop after a `pass` receipt, an honest user-question blocker, or a
   failed/tooling-blocked result with receipts.

Do not finish from image verification alone. A screenshot can catch visible
geometry mistakes, but it cannot prove that declared holes, bosses, slots,
spacing envelopes, source hashes, or rulepack constraints were checked.

## Confidence boundary

Only claim the level of confidence proved by the commands that actually ran:

- Passing geometry inspection and snapshot checks support geometric and visual
  review claims for the generated artifact.
- A `burr.receipt.v2` receipt with `outcome: pass` supports declared design-rule
  claims only for compatible rules and mechanical features Burr actually
  checked.
- An `incomplete` receipt blocks the verified claim even when every evaluated
  check passed.
- Neither geometry review nor Burr alone proves structural safety, process
  capability, tolerance stackups, compliance, material suitability, or print
  success.

If a feature has no Burr metadata, say so. If a rulepack does not cover the
feature or failure mode, say so. If Burr repair guidance is unavailable or too
ambiguous, use normal source-level diagnosis and report that the repair was not
sourced from an exact Burr receipt.

## Progressive references

Load these files only when their trigger applies:

- `references/burr-design-rule-loop.md` - Burr metadata, checking, repair, and
  reporting workflow.

Final responses should include generated files, Burr receipt paths, Burr outcome,
preview links when produced, verification snapshots, validation actually run,
assumptions, and caveats.
