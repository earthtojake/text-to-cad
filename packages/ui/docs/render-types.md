# Render types: the format → icon map

Binding for viewer work that touches more than one file format. The rule it exists to enforce:

> Shared viewer code never asks what a format **is**.

Every `renderFormat === RENDER_FORMAT.X` check is a place a new format must be hand-added and a
place an improvement to one format fails to reach the others. What a format does lives in its
renderer slice (`src/renderers/board`, `dxf`, `glb`, `mesh`, `robot` and `xbf`, one per file family) and is
described in [CAD renderer](cad-renderer.md#kit); the one thing the table below is read for is a
file's icon.

## The map

`packages/core/src/lib/renderCapabilities.js` is one frozen table keyed by render format
(`RENDER_FORMAT` in `packages/core/src/lib/fileFormats.js`). Its `iconKind` is what the file
list's icon comes from: `file-viewer/navigation/entryIconKind.js` looks an entry up in it, and
`EntryIcon.jsx` draws the result, the spinner for a file still loading and lucide's plain `File`
for every other kind.

| Render format | `iconKind` |
|---|---|
| `step` (`stp`), `xbf` | `step` |
| `stl` | `stl-mesh` |
| `3mf` | `3mf-mesh` |
| `glb` (`gltf`) | `glb-mesh` |
| `dxf` | `dxf` |
| `kicad_pcb` | `kicad_pcb` |
| `urdf`, `srdf`, `sdf` | `robot` |
| anything else | `step`, the table's default row |

An entry names its format twice, the catalog's `kind` and the resolved source format. When they
disagree, `entryIconKind` takes the first of `dxf`, `robot`, `stl-mesh`, `3mf-mesh`, `glb-mesh`
and `step` that either one names (an `.srdf` kind names `robot` itself), and a file still loading
is `loading` whatever its format. A new format adds its `RENDER_FORMAT` value, a row here and a
renderer slice; no shared component learns its name.

## Enforcement

`tests/python/global/test_viewer_format_capability_policy.py` counts `RENDER_FORMAT.X` checks and
`isMeshRenderFormat` / `isRobotRenderFormat` calls in the non-test sources of the engine document
renderer (`packages/ui/src/renderers/xbf`): both budgets are 0 and may not grow. It also asserts
that those sources, the file list's icon resolver (`file-viewer/navigation/entryIconKind.js`), the
shared explorer (`file-viewer/navigation/FolderExplorer.jsx`) and the file source that feeds it
(`cad-viewer/catalog.ts`) contain neither. `scripts/test/check-kit-boundaries.mjs`
(`npm run check:boundaries`) holds the kit the same way: `renderers/kit` names no file format and
imports no file-family core module, `renderCapabilities.js` among them
([the rule and its check](cad-renderer.md#kit)). The table has a unit test of its own,
`packages/core/src/lib/renderCapabilities.test.js`.
