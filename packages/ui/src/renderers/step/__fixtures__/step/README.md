# The STEP browser-test fixture

What a browser test has to serve to open one STEP in the viewer.
`StepRenderer.browser.test.mjs` serves it through
`renderers/harness/stepScenario.mjs`.

The model is `hinge_block`: a 20 × 20 × 10 mm **base** in `#3A6EA5` with a Ø6 mm
bore through it, and a 10 × 8 × 8 mm **arm** in `#D9772B` at x = 15, joined by
one revolute mate. Every property is there for a test:

| property | what it buys |
| --- | --- |
| two parts, two distinct colours | a part's pixels can be told from the other's, so "hidden", "exploded" and "posed" are measurements rather than guesses about total ink |
| the bore | a cylindrical face beside planar ones, so a face pick has something to report a diameter for |
| one revolute mate `hinge` (0…90°) | the panel's Position section, the Position tool and its one knob |
| one named pose `open` | the named-pose jump |
| one routine `swing` | its playbar in preview |

## The files, and which request each answers

| file | bytes | the request it answers |
| --- | ---: | --- |
| `assembly.json` | 3,165 | `GET /__cad/store?file=<tree>/assembly.json&documentHash=…` — the view descriptor. Carries `kind: "assembly-package"`, the `tree`, the `viewId`, the attested `producer`, two components (each naming its `part`), two occurrences and the model box. Every id is one the build minted: the root `o:895cdc947985`, the base `o:cec517897e79`, the arm `o:5da881c8dcfe`. |
| `components/f3f5f4facb11b472.selectors.json` | 7,876 | `GET /__tess_cache/<part>.selectors.json?object=…&maxBytes=…` for the base: its part record's `selectors`. cadgen's selector table (schema 6): each face's, edge's and vertex's name (its lineage: `f:hinge_block.make_box1.1`, the bore `f:hinge_block.make_cylinder1.1`, the cut's new rims `e:hinge_block.cut1.1` and `e:hinge_block.cut1.2`), the facts, adjacency, chains and tangent groups picking and measuring join to the mesh by ordinal. |
| `components/d4c6d71a49842756.selectors.json` | 6,126 | the same, for the arm: its own box's elements (`f:hinge_block.make_box1.1` … `.6`), its label naming the occurrence. |
| `components/<cid>.measures.json` | 354–616 | `POST /__cad/measure` for a face of that component: each face's exact area and centroid by ordinal, `{face, area, center}`, as cadgen measures them when a view asks (`parts.measure_face`). No selector table carries a face's area: the Reference panel's Area and the measure tool's chip ask for it. |
| `components/<cid>.glb` | 2,604–9,292 | the parts' display meshes (GLB bodies), one per component, each its part record's `glb`: what the harness's part store serves (`/__tess_cache/` probe, batch and single reads, by each component's `part`). |
| `hinge_block.step.json` | 2,247 | **no request at all.** The harness puts its `animation` section inline on the catalog entry, which is what the real scanner does, and the renderer plays the routine's keyframes straight from there; its tracks name the arm by its token. |
| `hinge_block.articulation.json` | 554 | **no request at all.** cadgen's articulation of the sidecar's kinematics (`cadgen.articulation.step_articulation` over `assembly.json` and the sidecar), which the harness puts inline on the catalog entry as `articulation`, as the real scanner does; the Position tool plays it. `tests/python/packages/cadgen/test_articulation.py` asserts it is what cadgen writes today. |

Total 32,834 bytes with the meshes, tables and measures. No Git attribute applies here (`git check-attr -a` on these
paths prints nothing), and the repository carries no LFS. Keep it that way — an
LFS pointer would be rejected by name at `renderAssetClient.js`'s readers.

The `.step` itself is **not** committed, because the viewer never fetches it:
the catalog names a store view, not the document.

## How the sidecar is bound

`read_source_sidecar` refuses a sidecar whose `schemaVersion` is not current or
whose `documentHash` is not the digest of the STEP bytes being resolved, and the
catalog entry then carries no `articulation` and no `animation` — so the file
silently has no Position section and nothing to play in preview. This one is bound: `schemaVersion` is 11 and
`documentHash` is
`5e4a74e9422639f2c2896929ca7f7c6899ccb9b2d27cd69652227752ecabd81e`, the SHA-256
of the generated `hinge_block.step`, which is also the `documentHash` in
`assembly.json`. Both were written by the build, not by hand.

## Regenerating

`source/hinge_block.py` is the model verbatim, its routine a Python clip.
`source/make_view.py` builds it in a scratch directory with a store of its own,
as a person builds it, and copies out everything the viewer is served: the view
descriptor (`assembly.json`, as `descriptor_for_view` serves it for the saved
document's tree), the document-bound sidecar, cadgen's articulation of its
kinematics, each component's part -- its display mesh and its selector
table -- read from the store under the part's key, and each of its faces' exact
area and centroid, measured as a view's request would have them. Every id in them is minted
by the build: the occurrences' tokens from the tree, the elements' names from
their lineage (the features of `hinge_block.py` that made them), so a rebuild of
the unchanged model mints the same ones. It takes a few seconds; run it from
the repository root with the repo's Python whenever the view schema, the sidecar
schema, the mesher, the selector table, the part key or the model moves:

```sh
.venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_view.py
```

When the STEP bytes or the view change, the component ids, `tree`, `viewId` and
`documentHash` change with them, and `stepScenario.mjs` reads every one of them,
the occurrences' tokens included, out of `assembly.json` rather than hard-coding
them; a sidecar schema move that leaves the STEP bytes alone rewrites
`hinge_block.step.json` only.
