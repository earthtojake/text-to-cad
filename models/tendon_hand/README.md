# Tendon Hand

This is the source-only tendon-driven right-hand research project. It has 24
joint degrees of freedom and 48 antagonistic tendon actuators. The model uses
millimetres, points the fingers along +Y, places the palm on +Z, and places the
thumb on -X.

The project was consolidated from the former
`models/assemblies/{src,STEP,validation,render}/anthropomorphic_hand` trees.
Generated STEP, GLB, video, screenshot, cache, and validation-output files are
deliberately absent. The committed files are enough to preserve the geometry
factories, model entry points, validation programs, design reports, render
modules, choreography generator, and standalone HTML presentation.

## Layout

- `src/` contains runnable CAD models, render-job JSON, design reports, and
  shared factories in `src/lib/`.
- `STEP/` is the generated geometry folder. Its small committed `.step.js`
  files are authored render modules; the R13 showcase module is generated and
  ignored because its solved keyframes are roughly 12 MB.
- `validation/` contains validation and regeneration programs. Its `.gitignore`
  keeps generated reports, checkpoints, logs, and NumPy data local.
- `website/` contains the standalone HTML presentation and its behavior test.
  The five multi-gigabyte animated GLBs it loads are generated and ignored.
- `tmp/` is the ignored destination for snapshots, videos, and review packets.

The engineering status is still work in progress. `src/README.md`,
`src/RESUME_STATUS.md`, and `src/GAUNTLET.md` record the current R13 checkpoint
and the distinction between completed mechanical checks and open visual or
motion acceptance.

## Environment

Run commands from the repository root. Use the repository development
environment so the checkout's `cadgen` and its JavaScript runtime stay in sync:

```sh
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt
./.venv/bin/python -m playwright install chromium
```

Animated GLB export uses the unreleased `cadgen glb build --animation` support,
and the showcase uses `deformTube`. A released cadgen without those features
cannot rebuild the motion assets.

## Rebuild CAD assets

Python files directly under `src/` are model entry points. A standalone review
model can be rebuilt by running its file; imports from `src/lib/` are shared
factories and do not need a separate build command:

```sh
./.venv/bin/python models/tendon_hand/src/pulley_review.py
./.venv/bin/python models/tendon_hand/src/runtime_fixture.py
```

List the full model catalog with:

```sh
find models/tendon_hand/src -maxdepth 1 -name '*.py' -print | sort
```

Some later entry points import earlier STEP or validation outputs. In
particular, R13 is an exact, frozen engineering checkpoint. The chronological
notes in `src/RESUME_STATUS.md` and `src/GAUNTLET.md` describe its status, but
they are not a build script.

`rebuild_manifest.json` is the machine-readable R13 dependency manifest. It
records all 51 frozen inputs, their byte counts, and SHA-256 digests. They total
424,298,044 bytes and are excluded from Git as generated CAD and validation
output. There is no external vendor CAD input. The authoritative local copy was
verified on 2026-09-10 in the untouched checkout at commit
`7aa3e85be76f305437abd3d7aba26e38b28e43cb`, under the legacy
`models/assemblies/{STEP,validation}/anthropomorphic_hand` layout. The files
are ignored rather than Git- or LFS-tracked, so the commit alone cannot restore
them.

On the machine where that checkout is available, import the exact checkpoint
from the legacy `models/assemblies` directory. The importer verifies every
source digest, copies the files to their ignored Tendon Hand paths, rewrites
only recorded absolute checkout paths inside JSON, and writes an ignored
receipt binding the installed files to the manifest:

```sh
./.venv/bin/python models/tendon_hand/rebuild.py import-checkpoint \
  --from /Users/jakefitzgerald/robots/text-to-cad/models/assemblies
./.venv/bin/python models/tendon_hand/rebuild.py check
```

For another machine, copy that legacy `models/assemblies` directory or a bundle
with the same layout, then pass its path to `--from`. The importer rejects a
missing, changed, or incomplete bundle before loading CAD.

Print the complete dependency-ordered final-asset recipe without executing it:

```sh
./.venv/bin/python models/tendon_hand/rebuild.py plan --video
```

After reviewing the plan, rebuild the exact final assets. Omit `--video` if the
optional MP4 is not needed:

```sh
./.venv/bin/python models/tendon_hand/rebuild.py run --video
```

The runner performs these stages in order:

1. verifies the complete checkpoint and its import receipt;
2. builds R13 once to write its body-frame manifest;
3. regenerates the indexed capstan overlay from those frames;
4. rebuilds the final R13 STEP with that fresh overlay;
5. validates every STEP placement;
6. generates the ignored R13 render module;
7. exports the five website GLBs (`fist`, `wave`, `pinch`, `signs`, `drive`);
8. optionally renders `tmp/showcase.mp4`; and
9. runs the HTML behavior test.

The equivalent root-model command, after checkpoint import, is:

```sh
./.venv/bin/python models/tendon_hand/src/hand_mechanical_candidate_r13.py
```

This writes `models/tendon_hand/STEP/hand_mechanical_candidate_r13.step` and
`models/tendon_hand/validation/mechanical_candidate_r13_frames.json`.
The frozen native base is byte-identical to the archived
`hand_progress_review.step`; its certificate names that source and binds the
STEP and 3,151-body frame manifest by SHA-256. No committed program recreates
the historical appearance manifest or the full set of accepted gate reports,
which is why the digest-checked archive import is required for an exact R13
rebuild. Earlier standalone component and review models remain rebuildable with
the same `python <model>.py` interface.

Validate or render any rebuilt STEP explicitly:

```sh
./.venv/bin/cadgen step inspect validate \
  models/tendon_hand/STEP/hand_mechanical_candidate_r13.step --every-placement
./.venv/bin/cadgen step snapshot \
  models/tendon_hand/STEP/hand_mechanical_candidate_r13.step \
  models/tendon_hand/tmp/r13.png
```

Render-job JSON files in `src/` rebuild the recorded review packets. For
example:

```sh
./.venv/bin/cadgen step snapshot \
  --job models/tendon_hand/src/mechanical_candidate_r13_render_job.json --json
```

## Rebuild animation and website assets

After the R13 STEP and its frame manifest exist, generate its render module.
The generator solves the common timeline, tendon routes, payout, moving guide
frames, and actuator transforms, then writes the ignored
`STEP/hand_mechanical_candidate_r13.step.js`:

```sh
./.venv/bin/python models/tendon_hand/validation/write_showcase_presentation.py
```

Export the five GLBs expected by `website/index.html`. The animation request
keeps the source clip name, bakes deforming tendons as morph targets, and drops
parts hidden at the first frame. Adjust `fps`, `seconds`, mesh tolerances, or
`deformTolerance` only when intentionally trading size, fidelity, and runtime
memory:

```sh
for clip in fist wave pinch signs drive; do
  ./.venv/bin/cadgen glb build \
    models/tendon_hand/STEP/hand_mechanical_candidate_r13.step \
    "models/tendon_hand/website/hand_${clip}.glb" \
    --animation "{\"clip\":\"${clip}\",\"fps\":30,\"deform\":\"morph\",\"deformTolerance\":1.0,\"drop\":[\"visible\"]}"
done
```

To render a shareable video instead of a GLB animation, cadgen needs `ffmpeg`
on `PATH`:

```sh
./.venv/bin/cadgen step snapshot \
  models/tendon_hand/STEP/hand_mechanical_candidate_r13.step \
  models/tendon_hand/tmp/showcase.mp4 \
  --animation showcase --video '{"fps":30,"quality":"review"}'
```

The website itself is committed, authored HTML and has no bundling step. The
five GLBs are its only generated runtime assets. Once they exist, test and
serve it with:

```sh
node --test models/tendon_hand/website/preview.behavior.test.mjs
./.venv/bin/python -m http.server 8820 --bind 127.0.0.1 \
  --directory models/tendon_hand/website
```

Open <http://127.0.0.1:8820/index.html>. A reload reads the current GLB files;
the page does not keep a persistent generated-asset cache.
