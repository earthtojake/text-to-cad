# cadpy

Shared Python runtime for STEP-backed and Python-backed CAD Viewer GLB/topology artifacts.

The package boundary is intentionally narrow: it owns artifact generation,
validation, selector/topology extraction, mesh settings, source hashing, and the
`cadpy-step-artifact` CLI. It also includes small generated-script helpers such
as `cadpy.assembly.AssemblyHelper`, which wraps native build123d labels, joints,
and compounds without owning skill-specific UX. Prompts, viewer UI, and snapshot
job orchestration stay in their owning skills.

## Local Development

Install it editable into the repo CAD runtime when working on the source
package directly:

```bash
./.venv/bin/python -m pip install -e packages/cadpy
```

After that, changes under `packages/cadpy/src/cadpy` are immediately visible to
local source checkouts that import the package directly.

The CAD skill's checked-in requirements install the generated, skill-local
package copy under `skills/cad/scripts/packages/cadpy`. The root Viewer carries
its generated copy under `viewer/packages/cadpy`. Refresh those copies with
`scripts/bundle/bundle-skill.sh cad` or `scripts/bundle/bundle-skill.sh cad-viewer`
after changing this package.

## Production Bundling

Build a wheel and install it into each skill's bundled Python environment during
packaging:

```bash
./.venv/bin/python -m build packages/cadpy
python -m pip install packages/cadpy/dist/cadpy-*.whl
```

The CAD and cad-viewer skills should depend on the package artifact they bundle,
not on `skills/cad` or the repository root. The generated skill runtimes bundle
installable packages under `skills/cad/scripts/packages/cadpy` and
`skills/cad-viewer/scripts/viewer/packages/cadpy`; production packaging can
also set `VIEWER_CAD_PYTHON` to a skill-local Python runtime with this package
installed.
