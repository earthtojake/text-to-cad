# The STEP browser-test fixture

What a browser test has to serve to open one STEP in the viewer, and nothing
else. `CadRenderer.browser.test.mjs` serves it through
`renderers/harness/stepScenario.mjs`.

The model is `hinge_block`: a 20 × 20 × 10 mm **base** in `#3A6EA5` with a Ø6 mm
bore through it, and a 10 × 8 × 8 mm **arm** in `#D9772B` at x = 15, joined by
one revolute mate. Every property is there for a test:

| property | what it buys |
| --- | --- |
| two parts, two distinct colours | a part's pixels can be told from the other's, so "hidden", "exploded" and "posed" are measurements rather than guesses about total ink |
| the bore | a cylindrical face beside planar ones, so a face pick has something to report a diameter for, and the modeling tree a cut feature to recognise |
| one revolute mate `hinge` (0…90°) | the Kinematics tab, the Pose tool and its one knob |
| one named pose `open` | the named-pose jump |
| one routine `swing` | the Animate tool and its playbar |

## The files, and which request each answers

| file | bytes | the request it answers |
| --- | ---: | --- |
| `assembly.json` | 3,010 | `GET /__cad/store?file=<tree>/assembly.json&documentHash=…` — the view descriptor. Carries `kind: "assembly-package"`, the `tree`, the `viewId`, the attested `surfaceProducer`, two components, two occurrences and the model box. |
| `components/552fc5fd1b854ab4.surf` | 13,966 | `GET /__cad/store?tree=…&surfaceInput=…&object=…` for the base. Exact surfaces; the client tessellates them. |
| `components/df492f79c6123df5.surf` | 10,478 | the same, for the arm. |
| `hinge_block.step.json` | 691 | **no request at all.** The harness puts it inline on the catalog entry as `sourceSidecar`, which is what the real scanner does, and the renderer compiles kinematics and animation straight from there. |

Total 28,145 bytes. Nothing here is LFS-tracked: `.gitattributes` matches
`*.step`, not `*.step.json`, and has no rule for `*.surf` or for `packages/**`
(`git check-attr -a` on these paths prints nothing). Keep it that way — an LFS
pointer would be rejected by name at `renderAssetClient.js`'s SURF reader, and
CI checks out without LFS.

The `.step` itself is **not** committed, because `*.step` is LFS and because the
viewer never fetches it: the catalog names a store view, not the document.

## How the sidecar is bound

`read_source_sidecar` refuses a sidecar whose `schemaVersion` is not current or
whose `documentHash` is not the digest of the STEP bytes being resolved, and the
catalog entry then carries no `sourceSidecar` — so the file silently has no
Kinematics tab and no Animate tool. This one is bound: `schemaVersion` is 9 and
`documentHash` is
`3c1e7edf8593d6019706ff355445199971b740e2bd0661eda6ade9b961082f58`, the SHA-256
of the generated `hinge_block.step`, which is also the `documentHash` in
`assembly.json`. Both were written by the build, not by hand.

## Regenerating

`source/hinge_block.py` is the model verbatim. Generated with cadgen **0.6.5**
(build123d 0.11.1, OCP 7.9.3.1, scheme 19, SURF format 2), in a scratch
directory, with a cache of its own:

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

Regenerate when the SURF format, the view schema or the sidecar schema moves;
the component ids, `tree`, `viewId` and `documentHash` all change with it, and
`stepScenario.mjs` reads every one of them out of `assembly.json` rather than
hard-coding them.
