# Manual validation models

`models/tests` on cadgen 0.8: the three cases its README listed. **CI
tests must never read, import, build, or depend on anything here**: automated tests
make their own small fixtures in fresh temporary directories.

Agents may use these models for manual browser reviews, reproducing edge cases,
checking exports and debugging new features. They are small and quick to rebuild.
Each case is a `@model`; a run writes nothing, and prints the document's id and page.

## Cases

| Folder | Model | Manual checks |
| --- | --- | --- |
| `render_floor/` | `floor_positions` | Three coloured blocks above, across and below Z=0. Render's floor stays at the authored origin; aligning to the lowest point is an explicit option. |
| `viewer_concurrency/` | `assembly` | A 32-part drilled-plate assembly. Change `REVISION` and rebuild while the viewer is loading to check update handoffs, progress and replacement geometry. |
| `unified_annotations/` | `annotation_fixture` | An 11-part assembly: brushed steel on the base and shaft (each keeping its own colour), a blue paint on the arm (its own colour green at alpha 0.6; the paint's blue at opacity 0.5 is what shows), the arm's `swing` joint and the shaft's `lift`, a configuration (`open`: swing 45) and a motion (`demo`: the shaft 8 mm up, 8 mm down and home over 4 s, ending where it starts, so a player repeats it as the old looping clip ran). Check materials, Position, motion in both view modes, a motion-only edit (the mechanism rewritten, no prototype converted), snapshots and the GLB clip. |

## Run manually

From each case's folder, with the engine's environment (`cadgen` on the path):

```bash
# Keep manual runs on a daemon of their own.
export CADGEN_ENGINE_DIR="$(mktemp -d /tmp/cadgen-manual-engine.XXXXXX)"
python source.py                     # render_floor/, viewer_concurrency/
python annotation_fixture.py         # unified_annotations/
cadgen snapshot "$ID" /tmp/open.png --pose open     # ID: the id: line the run printed
cadgen export "$ID" /tmp/annotations.glb            # demo, baked as a clip
```

## The port

- `@step(out=...)` -> `@model`: a case writes nothing; export a file of it on request.
- `unified_annotations`: the sidecar's `materials=` are `Material` values on the parts
  (steel the catalogue's, in the old finish, `color=None`; the paint its own, with its
  colour); the `swing` mate is a build123d revolute joint and the `open` pose a
  configuration; the clip, which moved the shaft by hand, is a motion of a new prismatic
  joint, `lift` (-8 to 8 mm). The old viewer multiplied the paint's opacity into the
  arm's (0.3); a part with a material wears the material's colour, so it shows 0.5.

## Not ported

- `joint_playground/joint_playground.urdf`: an authored URDF of primitives, no model,
  and no doc names it. It is kept in `unported/`, and the engine's snapshot draws it as
  it is (`cadgen urdf snapshot models/tests/unported/joint_playground/joint_playground.urdf out.png`).
