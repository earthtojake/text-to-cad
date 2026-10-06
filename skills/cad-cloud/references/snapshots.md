# Snapshots

`cad_snapshot(build, file, args, format)` renders one file of a build in a
sandbox. `build` is an id or a build link; `file` is a viewable file of the build
(STEP, STL, 3MF, GLB, DXF, URDF, SRDF or SDF) and defaults to the build's main
output, or to the file a link names; `format` is `png` (default) or `svg`; and
`args` is a list of the flags that follow the output path in the command it runs,
one element per word. The server supplies the file and the output path, so these
two are the same request:

```
cadgen snapshot STEP/bracket.step tmp/review.png --display render --camera front
```

`file: "STEP/bracket.step"`, `args: ["--display", "render", "--camera", "front"]`.
A snapshot reads a saved file and never runs model scripts, so the build must be
finished. Each user runs one snapshot or inspection at a time. A snapshot that
outlasts about 40 s returns a job id: poll it with `cad_status`. The result
carries the image, and a URL for it that you can share.

## Policy

Every created or visibly updated part or assembly gets at least one reviewed
snapshot of its STEP, or of its mesh when no STEP is declared. Passing geometry
checks does not waive it, and the thumbnail `cad_build` returns counts only when
it shows the change. Skip a snapshot when no visible geometry was created or
updated (a pure export, a source change that leaves the geometry alone, an
inspection-only task, a failed build), and report the reason and the checks
that still ran.

Do not loop on snapshots. Render again when a repair changed visible geometry or
a specific finding needs confirming.

## Choosing views

Pick views that expose the features under review. One may be enough. Add an
opposing view for hidden exterior features, an orthographic view for a pattern
or a silhouette, and a section for bores, cavities, passages, blind holes,
enclosures and wall or floor relationships. No fixed set of views proves every
face or feature is correct.

## Flags

The server passes these flags and refuses any other by name; give a value as the
next element or as `--flag=value`.

| Flag | Meaning |
| --- | --- |
| `--display NAME` | `solid` (default), `render`, `xray`, `hidden-line`, `wireframe` or `grid`; or grouped display JSON as one element. `render` is a photographic view with a perspective camera; `grid` is Solid on a measuring grid. |
| `--camera VIEW` | A preset (`front`, `back`, `left`, `right`, `top`, `bottom`, `iso`), an `azimuth:elevation` pair such as `30:20`, or camera JSON (`position`, `target`, `up`, `direction`, `zoom`, `orthographicHalfHeight`). Default: orthographic isometric. |
| `--mode section --section PLANE[:OFFSET]` | Cut with a plane and draw the outline. `PLANE` is `XY`, `XZ` or `YZ`, the two axes the plane contains (default `XY`); `OFFSET` moves it along its normal in model units (default 0), so `XZ:12.5` cuts at Y = 12.5. |
| `--focus REF`, `--hide REF` | Render an occurrence at full opacity and ghost the rest, or leave it out. Repeatable; STEP only. `REF` is `#o1.2` or a label such as `#pin_left`. |
| `--width N`, `--height N` | Pixels, 16 to 4096, overriding the size profile. |
| `--size-profile NAME` | `simple` 1200x900, `simple-square` 1024x1024, `diagnostic` and `labeled` 1600x1200 (default), `assembly` 1800x1200, `assembly-large` 1920x1440, `presentation` and `contact-sheet` 2400x1600, `presentation-large` 2800x1800. |
| `--view-labels` | Burn the view label into the image. |
| `--kinematics POSE` | Pose a STEP model that declares kinematics: a preset name or `{dof: value}` JSON. |
| `--animation CLIP --time SECONDS` | One still frame of a clip a STEP model declares. |
| `--joint-values JSON` | Pose a robot description (URDF, SRDF or SDF) with `{joint: degrees}`. |

Grouped display JSON takes the groups `camera` (`projection`, `focalLength`),
`surfaces` (`style`, `colorMode`, `color`, `opacity`), `edges` (`visibility`,
`color`), `lighting`, `background` (`color`, `opacity`), `floor` (`placement`,
`finish`, `color`, `opacity`), `grid` and `axes`. Omitted groups inherit the
preset, and every group takes a boolean `enabled`. For example:

```
cadgen snapshot STEP/bracket.step tmp/review.png --display '{"mode":"render","floor":{"enabled":false}}'
```

Unknown keys and out-of-range values are refused by name, so a misspelling
cannot render the wrong thing quietly. `--job` and `--video` are not available.

## Formats

A view writes PNG. A section also writes SVG, so `format: "svg"` needs
`--mode section`; any other request for SVG is refused. A section is STEP only
and takes no kinematics or Render display, and a plane that misses the model
renders an empty drawing with a warning. A PNG comes back as an image; a small
SVG comes back as text.

STL, 3MF and GLB files take `solid` and `render` only. They have no CAD edges,
parts to explode or solids to section, so `xray`, `hidden-line`, `wireframe`,
edges, `--mode section`, `--focus`, `--hide` and `--kinematics` are refused by
name. A DXF is drawn flat and head on: it takes no camera and only the
appearance of a display.

## Reading a snapshot

Visual review is diagnostic, not authoritative. Turn each concern into a
measurement with `cad_inspect` before calling it resolved:

- A hole pattern looks asymmetric: measure hole centers and compare offsets.
- A lid or child part looks offset: inspect frames and mating deltas.
- A gusset, boss, standoff or rib may be floating: check solid count, labels,
  contact and the relevant distances.
- A cavity, bore or blind hole looks wrong: take a section, then measure wall
  thickness, depth or the through-condition.
- A repeated pattern looks uneven: measure pattern centers, angular spacing or
  occurrence frames.

A periodic cylinder or revolved face has a seam edge that can show in linework.
Use a shaded display or another camera to tell a seam from a crack.
