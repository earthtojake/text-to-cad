# The STEP browser-test fixture

What a browser test has to serve to open one STEP in the viewer, and nothing
else. `StepRenderer.browser.test.mjs` serves it through
`renderers/harness/stepScenario.mjs`.

The model is `hinge_block`: a 20 × 20 × 10 mm **base** in `#3A6EA5` with a Ø6 mm
bore through it, and a 10 × 8 × 8 mm **arm** in `#D9772B` at x = 15, joined by
one revolute mate. Every property is there for a test:

| property | what it buys |
| --- | --- |
| two parts, two distinct colours | a part's pixels can be told from the other's, so "hidden", "exploded" and "posed" are measurements rather than guesses about total ink |
| the bore | a cylindrical face beside planar ones, so a face pick has something to report a diameter for, and the modeling tree a cut feature to recognise |
| one revolute mate `hinge` (0…90°) | the panel's Position section, the Position tool and its one knob |
| one named pose `open` | the named-pose jump |
| one routine `swing` | its playbar in preview |

## The files, and which request each answers

| file | bytes | the request it answers |
| --- | ---: | --- |
| `assembly.json` | 3,010 | `GET /__cad/store?file=<tree>/assembly.json&documentHash=…` — the view descriptor. Carries `kind: "assembly-package"`, the `tree`, the `viewId`, the attested `surfaceProducer`, two components, two occurrences and the model box. |
| `components/552fc5fd1b854ab4.surf` | 13,966 | `GET /__cad/store?tree=…&surfaceInput=…&object=…` for the base. Exact surfaces: what feature recognition reads. |
| `components/df492f79c6123df5.surf` | 10,478 | the same, for the arm. |
| `components/552fc5fd1b854ab4.selectors.json` | 8,355 | the same route, by the table's own digest (the `selectors` of a `POST /__cad/surfaces` ready row), for the base. cadgen's selector table: the ids, facts, adjacency, chains and tangent groups picking and measuring join to the mesh. |
| `components/df492f79c6123df5.selectors.json` | 6,499 | the same, for the arm. |
| `components/<cid>.l<level>.glb` | 3,044–15,064 | the store's meshes (GLB bodies), one per component and LOD level 0–3: what the harness's mesh store serves (`/__tess_cache/` probe, batch and single reads), and what a `POST /__cad/surfaces` naming a tessellation answers with. |
| `hinge_block.step.json` | 1,922 | **no request at all.** The harness puts it inline on the catalog entry as `sourceSidecar`, which is what the real scanner does, and the renderer reads the kinematics and the routine's keyframes straight from there. |

Total 96,202 bytes with the meshes and tables. No Git attribute applies here (`git check-attr -a` on these
paths prints nothing), and the repository carries no LFS. Keep it that way — an
LFS pointer would be rejected by name at `renderAssetClient.js`'s SURF reader.

The `.step` itself is **not** committed, because the viewer never fetches it:
the catalog names a store view, not the document.

## How the sidecar is bound

`read_source_sidecar` refuses a sidecar whose `schemaVersion` is not current or
whose `documentHash` is not the digest of the STEP bytes being resolved, and the
catalog entry then carries no `sourceSidecar` — so the file silently has no
Position section and nothing to play in preview. This one is bound: `schemaVersion` is 10 and
`documentHash` is
`3c1e7edf8593d6019706ff355445199971b740e2bd0661eda6ade9b961082f58`, the SHA-256
of the generated `hinge_block.step`, which is also the `documentHash` in
`assembly.json`. Both were written by the build, not by hand.

## Regenerating

`source/hinge_block.py` is the model verbatim, its routine a Python clip. The
view descriptor and the two `.surf` files were generated with cadgen **0.6.5**
(build123d 0.11.1, OCP 7.9.3.1, scheme 19, SURF format 2) and stay at format 2
on purpose: every reader still reads format 2 (an older build may have pinned
one in an eager-only component's identity), and this fixture is where the
browser tests read one end to end, while core's `lib/surf/fixtures` are format 3.
The sidecar was rewritten at schema 10 by a later build of the same model, whose
STEP bytes did not change, so `documentHash` and every id stayed as they were.
Build in a scratch directory, with a cache of its own:

```sh
mkdir -p /tmp/step-fixture/{src,STEP,cache} && cd /tmp/step-fixture
cp <this dir>/source/hinge_block.py src/
CADGEN_CACHE_DIR=$PWD/cache <repo>/.venv/bin/python src/hinge_block.py
```

That writes `STEP/hinge_block.step` and `STEP/hinge_block.step.json`, and fills
the store. Then copy out the four served files: the view descriptor is
`descriptor_for_view(tree, document_hash=…)` from `cadgen.store.view` for the
tree that `document_entry_for_hash(sha256(step_bytes))` names, and each `.surf`
is the store object named by `surfaceObject` in the **materialized** view
(`materialize_view_surfaces`), read through `cadgen.store.objects.object_path`.
The served descriptor is the unmaterialized one — that is deliberate, and is why
the harness must implement `POST /__cad/surfaces`.

The meshes are cadgen's own: `source/make_meshes.py` rebuilds the two parts,
meshes them with cadgen's producer at each LOD level, and writes them in the
committed `.surf`s' ordinals (a newer build orders the base's edges differently;
the script matches them by centre and length). Run it from the repository root
with the repo's Python whenever the mesh format or the mesher moves:

```sh
.venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_meshes.py
```

The selector tables are cadgen's own too: `source/make_selectors.py` rebuilds
the two parts, builds each table from its exact BREP and SURF
(`cadgen._internal.selector_table`), and writes it in the committed `.surf`'s
ordinals, matched as the meshes are. Run it after `make_meshes.py`, and
whenever the table's schema or scheme moves:

```sh
.venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_selectors.py
```

Regenerate when the view schema or the sidecar schema moves, or when readers
stop reading SURF format 2.
When the STEP bytes or the view change, the component ids, `tree`, `viewId` and
`documentHash` change with them, and `stepScenario.mjs` reads every one of them
out of `assembly.json` rather than hard-coding them; a sidecar schema move that
leaves the STEP bytes alone rewrites `hinge_block.step.json` only.
