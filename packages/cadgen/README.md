# cadgen

STEP-first CAD artifact generation runtime for CAD agent skills, built on
[build123d](https://github.com/gumyr/build123d) and OCCT.

The package boundary is intentionally narrow: it owns artifact generation,
validation, selector/topology extraction, mesh settings, source hashing, and the
`cadgen-step-artifact` CLI. It also includes small generated-script helpers such
as `cadgen.assembly.AssemblyHelper`, which wraps native build123d labels, joints,
and compounds without owning skill-specific UX. Prompts, viewer UI, and snapshot
job orchestration stay in their owning skills.

`cadgen` is developed in
[earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) and was
previously named `cadpy` inside that repository.

## Public API

The supported import surface is the root `cadgen` exports plus the top-level
`cadgen.*` modules:

- Generator-script helpers: root exports (`AssemblyHelper`, `MateRelation`,
  `MateTarget`, `label_text`, `label_shape`, `target`,
  `ensure_step_glb_artifact`, `validate_step_glb_artifact`), `cadgen.assembly`,
  and `cadgen.step_scene` (`import_step`, `load_step_scene`, `located_shape`,
  `occurrence_selector_id`, `scene_occurrence_shape`).
- Generator-script helpers (2D): `cadgen.sources` (`load_source_module`) and
  `cadgen.flatten` (planar-face projection/unfold, contour emission, kerf
  offsetting) for `.dxf.py` drawing generators.
- Skill CLI surface: `cadgen.generation` (`generate_step_targets`,
  `generate_dxf_targets`, `targets_include_output_pairs`), `cadgen.catalog`,
  `cadgen.metadata`, `cadgen.analysis`, `cadgen.lookup`, `cadgen.cad_ref_syntax`,
  `cadgen.selector_types`, `cadgen.reporting`, `cadgen.cli_logging`,
  `cadgen.render`, `cadgen.step_artifacts`, `cadgen.step_targets`,
  `cadgen.step_export`, `cadgen.drawing_checks` (DXF drawing validation), and
  `cadgen.drawing_render` (DXF render payload + SVG snapshots).
- Process entry points: `cadgen-step-artifact`, `python -m cadgen.step_artifact`,
  `python -m cadgen.step_export_target`, and `python -m cadgen.dxf_artifact`.

Everything under `cadgen._internal` is private implementation (the STEP scene,
generation, GLB/topology, and export engines live there) with no import
stability between releases; `cadgen.generation` and `cadgen.step_scene` are
thin facades over those engines that re-export only the supported names.

## Install

Released versions are published to PyPI by the repository's `Release` workflow;
the package version always matches the CAD plugin release version:

```bash
python -m pip install cadgen
```

Production skill bundles pin the exact release version in their
`requirements.txt` (for example `cadgen==0.4.0`) and keep a vendored copy of
this package as an offline fallback:

```bash
python -m pip install ./scripts/packages/cadgen
```

## Local Development

Install it editable into the repo CAD runtime when working on the source
package directly:

```bash
./.venv/bin/python -m pip install -e packages/cadgen
```

After that, changes under `packages/cadgen/src/cadgen` are immediately visible to
local source checkouts that import the package directly.

On `develop`, the CAD skill and root Viewer point at this package through the
development symlinks `skills/cad/scripts/packages/cadgen` and
`viewer/packages/cadgen`. Keep those links intact with
`scripts/dev/setup-symlinks.sh --check`.

## Production Bundling

Build a wheel and install it into each skill's bundled Python environment during
packaging:

```bash
./.venv/bin/python -m build packages/cadgen
python -m pip install packages/cadgen/dist/cadgen-*.whl
```

The CAD and cad-viewer skills should depend on the package artifact they bundle,
not on `skills/cad` or the repository root. Production packaging vendors
installable packages under `skills/cad/scripts/packages/cadgen` and
`skills/cad-viewer/scripts/viewer/packages/cadgen`; production packaging can also
set `VIEWER_CAD_PYTHON` to a skill-local Python runtime with this package
installed. Production skill bundles install `cadgen==<release version>` from
PyPI first and fall back to the vendored copy when offline.
