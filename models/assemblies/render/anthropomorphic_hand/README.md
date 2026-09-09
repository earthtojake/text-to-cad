# Tendon hand presentation

Standalone presentation of the five existing animated GLBs. The interface is a
local HTML page; no CAD server or model regeneration is needed to view it.

The complete work was transferred from
`.claude/worktrees/topology-feedback-claude-code-fb0c1a` at `fd3227924`, including
its uncommitted files, on 2026-09-09. The source worktree is unchanged. Transfer
and asset integrity records are in `tmp/tendon-preview-transfer/` in this checkout.

The page keeps the source preview's Three.js version, GLB geometry, material
assignment, lighting, camera framing functions, and render loop. The redesign
changes HTML/CSS: one right-hand inspector, compact transparent playback controls,
and a blue accent. A camera projection offset centers the model in the available
space to the left of the inspector while retaining the full-width backdrop.
Turntable and Bowden sheaths default to off. The loading change prepares all five scenes and
warms their rendering during startup. Motion selection is synchronous: it swaps
prepared scenes, preserves the camera and orbit target, and resets the selected
animation to time zero, paused. Visibility settings carry across motions.

The original GLBs total 5.1 GiB. They are loaded and prepared sequentially during
startup, then retained for immediate switching. This uses more memory than a
single-motion preview. A reload reads the current files directly; there is no
persistent browser asset cache that can serve an obsolete export.

Serve the preview from the repository root:

```sh
./.venv/bin/python -m http.server 8820 --bind 127.0.0.1 \
  --directory models/assemblies/render/anthropomorphic_hand
```

Open <http://127.0.0.1:8820/index.html>.

Focused behavior checks:

```sh
node --test models/assemblies/render/anthropomorphic_hand/preview.behavior.test.mjs
```

This presentation does not change the hand's engineering acceptance status or
claim that the original final pose/explode gauntlet has passed.
