# cadjs

`cadjs` is the shared JavaScript runtime for CAD Viewer, documentation previews,
and generated snapshot browser assets. It owns reusable parsing, scene-building,
explicit-CAD rendering, STEP topology, selector, mesh, robot-description, and
artifact helpers without depending on React or application chrome.

Implicit CAD model loading, shader rendering, snapshots, SDF sampling, and
mesh exports live in the sibling `implicitjs` package. Consumers that need
implicit CAD should depend on `implicitjs` directly alongside `cadjs`.

## Install

In this workbench, consumers link the package directly:

```json
{
  "dependencies": {
    "cadjs": "file:../packages/cadjs"
  }
}
```

The package exports source files so local consumers can alias or install it and
pick up edits without copying generated bundles.

## Layout

- `src/index.js`: public package entrypoint.
- `src/common/`: browser-safe render pipeline used by interactive viewer,
  docs previews, and snapshot browser runtime.
- `src/lib/`: lower-level first-party helpers for assets, formats, mesh
  decoding, selector runtimes, STEP sidecars, and URDF/SRDF/SDF.
- `src/lib/viewer/`: shared non-React 3D viewer runtime helpers such as picking,
  clipping, drawing geometry, reference geometry, stage theme, scene scale, and
  visual state.
- `scripts/run-tests.mjs`: package test discovery and Node test runner wrapper.
- `docs/`: reference docs for package-owned APIs.

Tests live beside the modules they cover as `*.test.js` or `*.test.mjs`.

## Boundaries

Keep this package UI-framework agnostic. Do not add React components, Tailwind
helpers, browser workbench state, or CAD Viewer chrome utilities here. Those
belong in consumer apps such as `viewer/`.

Prefer moving logic into `cadjs` when it is reusable across:

- interactive CAD Viewer rendering,
- docs or marketing previews,
- generated snapshot browser runtime,
- testable CAD parsing or sidecar preparation.

Prefer moving implicit model, shader, snapshot, SDF, or mesh-export behavior
into `implicitjs` instead.

Keep app-specific workflows in the app. A useful rule of thumb: `cadjs` should
understand CAD data and rendering state, while `viewer/` should understand user
interface and product workflow.

## Commands

From this package directory:

```bash
npm test
```

From the workbench repository root:

```bash
npm --prefix packages/cadjs test
```

The test command discovers all `*.test.js` and `*.test.mjs` files under
`src/`. To run one file:

```bash
node scripts/run-tests.mjs src/lib/themeSettings.test.js
```

## Reference

- [Render pipeline](./docs/render-pipeline.md): `loadSource`, `buildModel`,
  `renderModel`, and `captureModel` stages shared by viewer, docs, and
  snapshots.
