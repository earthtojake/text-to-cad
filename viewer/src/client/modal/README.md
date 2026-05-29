# Modal vibration preview

A standalone page (`viewer/modal.html` → `modalDemo.js`) that renders the
animated **modal GLB** produced by `cadpy_fea modal --modal-glb` and adds an
interactive "pluck":

- **Pluck (drag):** grab any point and drag — the part deforms as the
  minimum-strain-energy blend of mode shapes that makes that point follow the
  cursor (`solveDragWeights`). Release and it rings down as a free modal
  superposition, with the **flick velocity** carried into the modal initial
  velocity and the **material's real damping** setting the decay
  (`ModalSuperposition`). Slow-mo defaults to 50× and the slider reaches
  real-time.
- **Play mode:** play a single mode's baked animation clip (`ModalPlayer`).

All of the physics lives in the framework-agnostic, unit-tested cadjs engine
(`cadjs/common/modalInteraction.js`, `modalInteractionController.js`,
`modalAnimation.js`); this page is a thin three.js host.

## Run

```bash
# 1. generate a modal GLB next to a STEP part
./.venv/bin/python skills/cad/scripts/fea modal part.step \
    --material pla --fixed outer --modes 6 --modal-glb viewer/public/spring_pla.glb

# 2. serve the viewer and open /modal.html (defaults to /spring_pla.glb;
#    override with ?glb=/your.glb)
npm --prefix viewer run dev
```

GLBs under `viewer/public/` are generated artifacts and are git-ignored.

## Static build (e.g. Cloudflare Pages)

```bash
viewer/node_modules/.bin/esbuild viewer/src/client/modal/modalDemo.js \
    --bundle --format=esm --alias:cadjs=packages/cadjs/src --outfile=dist/bundle.js
# ship dist/bundle.js + a copy of modal.html (script src -> ./bundle.js) + the .glb
```
