# Tendon hand presentation

Standalone presentation for the five generated animated GLBs. The interface is
a plain local HTML page. Once the GLBs have been rebuilt beside `index.html`, no
CAD server or web bundler is needed to view it. See the project-level
`../README.md` for the exact CAD, render-module, GLB, video, test, and serving
commands.

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
  --directory models/tendon_hand/website
```

Open <http://127.0.0.1:8820/index.html>.

Focused behavior checks:

```sh
node --test models/tendon_hand/website/preview.behavior.test.mjs
```

This presentation does not change the hand's engineering acceptance status or
claim that the original final pose/explode gauntlet has passed.
