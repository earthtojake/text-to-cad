# STEP generation

Read this file when generating or regenerating STEP/STP artifacts from build123d Python source or from direct STEP/STP targets.

## Contents

- Tool
- Generated Python source
- Direct STEP/STP targets
- Adjacent CAD Viewer Artifacts
- Post-generation inspection
- Generation checklist

## Tool

The launcher lives in the CAD skill directory:

```bash
python scripts/step [--kind {part|assembly}] [--skip-step-write] targets... [flags]
```

Use explicit target paths only. Target paths are resolved from the command cwd unless absolute. When running from a workspace root, prefix the launcher path with the CAD skill directory; when running from the skill directory, pass absolute or correctly relative workspace target paths. Do not rely on directory-wide generation.

Plain generated Python targets write sibling `.step` outputs. Use `-o`/`--output` only with one plain generated Python target, or use `SOURCE.py=OUTPUT.step` positional pairs for per-target custom outputs. Paired output paths resolve from the command cwd and are valid only for generated Python sources, not direct STEP/STP inputs.

Do not put output paths in the `gen_step()` return value. The supported path controls are the sibling default, `-o`/`--output`, and `SOURCE.py=OUTPUT.step`.

## Generated Python source

Generated build123d sources should define:

```python
def gen_step():
    ...
    return step_ready_shape_or_labeled_compound
```

Generated Python targets infer their kind from the source metadata and `gen_step()` return value; pass the source path directly. When a generator exists, this is the preferred way to run `scripts/step`.

```bash
python scripts/step path/to/part.py
python scripts/step path/to/part.py --skip-step-write
python scripts/step path/to/part.py -o path/to/custom.step
python scripts/step path/to/a.py=out/a.step path/to/b.py=out/b.step
python scripts/inspect refs path/to/part.step --facts --planes --positioning
```

```bash
python scripts/step path/to/assembly.py
python scripts/inspect refs path/to/assembly.step --facts --planes --positioning
```

Passing a generated assembly `.step` directly treats it as imported native STEP. Pass the `.py` assembly source when source-level assembly composition must be preserved.

For generated build123d assemblies, prefer `cadpy.assembly.AssemblyHelper` in the Python source so native labels, named mate frames, and source-level relationships are preserved before STEP export.

## Direct STEP/STP targets

Use direct STEP/STP targets only when the generator is unavailable or the user explicitly identifies a STEP/STP file as the target:

```bash
python scripts/step --kind part path/to/imported.step
python scripts/inspect refs path/to/imported.step --facts --planes --positioning
```

Direct targets can use sidecar mesh flags, but generator targets remain preferred when a generator exists. Read `supported-exports.md` for STL and 3MF sidecars.

## Adjacent CAD Viewer Artifacts

`scripts/step` generates adjacent hidden CAD Viewer GLB/topology artifacts as part of the normal part/assembly build. These artifacts support CAD Viewer GUI review, `$cad-viewer` workflows, and CAD `inspect` refs. They are not optional in the STEP workflow.

For Python `gen_step()` targets, hidden GLB/topology artifacts are Python-backed (`sourceKind: "python"`) whether the command also writes the sibling `.step` file or runs with `--skip-step-write`. `--skip-step-write` skips writing the sibling `.step` file and writes only the hidden GLB/topology artifact using the logical same-stem STEP identity. This mode is valid only for Python generator targets and cannot be combined with STEP output overrides. Direct STEP/STP targets remain STEP-backed (`sourceKind: "step"`).

After generation, hand the explicit STEP/STP output path and any requested `$cad-viewer`-supported sidecar paths to `$cad-viewer` when available and return the links it prints.

## Post-generation inspection

Run lightweight inspection after generation with `scripts/inspect`.

Rules:

- Use facts and plane grouping for normal generation.
- Add positioning facts when the model has mating faces, assembly children, datums, or repeated features.
- Add topology only when selector enumeration is needed; it can be expensive on large models.

Recommended inspection:

```bash
python scripts/inspect refs path/to/model.step --facts --planes --positioning
```

For selector-heavy validation:

```bash
python scripts/inspect refs path/to/model.step --topology
```

## Generation checklist

Before running the command:

- Confirm the user request has been converted into a natural-language CAD brief.
- Confirm the source defines `gen_step()`.
- Prefer the Python generator over a generated STEP/STP file when both are available.
- Confirm native labels are assigned for exported parts, assembly children, mate datums, and any retained feature shapes.
- Confirm the target path is explicit.
- Confirm expected bbox, labels, and positioning checks are known.

After running the command:

- Confirm the process succeeded.
- Confirm the STEP file exists and is non-empty, unless the command intentionally used `--skip-step-write`.
- When `--skip-step-write` was used, confirm the hidden Python-backed GLB/topology artifact exists instead.
- Run the relevant `scripts/inspect` command and parse its output.
- Hand off generated STEP/STP paths and requested `$cad-viewer`-supported sidecar paths to `$cad-viewer` when available and return its link(s), or report why they are unavailable.
- Continue with targeted inspection if facts/planes are insufficient.
