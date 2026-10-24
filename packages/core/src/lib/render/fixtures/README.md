# GLB fixtures

The GLBs the core and UI suites open, kept as bytes.

`pair.glb` and `pair.slide.glb` are cadgen 0.8.0's exports of `pair`: two boxes, in
millimetres, Z up. `base` is a 20 mm cube from the origin to (20, -20, 20), red (#D02020)
in a polished finish (roughness 0.05, metalness 1); `rider` is a 10 mm cube from
(30, -10, 0) to (40, 0, 10), blue (#2040D0). `pair.glb` is the static export
(colour-grouped primitives); `pair.slide.glb` the animated one, with the clip `slide`,
which moves the rider 60 mm along +X over one second and holds there (one node per
occurrence, `o1.1` the base and `o1.2` the rider, the rider under the clip's pivot, keyed
CUBICSPLINE). The pipeline that wrote them is gone, and with it their generator:
`git log --diff-filter=D -- packages/core/src/lib/render/fixtures/make_fixtures.py` names
the commit that deleted it. They move to the engine's GLB export when the suites that
open them do.

`cube.meshopt.glb` is a unit cube (12 triangles, #3366CC), welded, quantized
(`KHR_mesh_quantization`) and meshopt-compressed (`EXT_meshopt_compression`, required):
cadgen writes no compressed GLB, but a GLB a person opens can be one, and the loader
decodes it. It was written by the JS writer this repository once kept for test fixtures
(`git log --diff-filter=D -- packages/core/src/lib/glb/writeGlb.js` names the commit that
deleted it). Both extensions are ratified glTF, so any writer of them can replace it
(meshoptimizer's `gltfpack -c` over a cube) as long as `glbMeshoptRoundTrip.test.js` still
describes it.

`animation.glb` and `motion.glb` are the engine's GLB export, baked by today's cadgen from the
two small models `tests/python/packages/cadgen/engine/test_animation.py` writes (`CHANNELS` and
`MOTION`), and that test holds them to what the baker writes now, key for key. `animation.glb`
carries the motion-free box's `animation()`, `showcase` (2 s): every channel path (translation,
rotation, scale) authored under every interpolation (STEP, LINEAR, CUBICSPLINE) and a `pose`
through the lid's hinge, written as the engine writes every GLB's keys, STEP as baked and the rest
LINEAR within a tenth of a millimetre and of a degree of the bake; `motion.glb` a box whose only
animation is its motion `open_close`, an AP242 configuration sequence. `bakedGlbAnimation.test.js` runs the Khronos glTF-Validator over both and
plays them with three.js. When the baker changes, write them again:
`CADGEN_WRITE_FIXTURES=1 .venv/bin/python -m unittest tests.python.packages.cadgen.engine.test_animation`.
