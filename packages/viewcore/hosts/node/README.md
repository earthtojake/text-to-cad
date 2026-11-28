# hosts/node (prototype)

The view core under Node: `viewcore.mjs` loads the module with the browser host's own loader and WASI shim, and
`serve.mjs` is a job server that answers the engine's pool jobs from it, in one long-lived process of a few tens of
megabytes. Nothing in cad starts it yet.

    node serve.mjs [VIEWCORE_WASM]        # default: ../../dist/viewcore.wasm (scripts/core.sh)

It needs Node 22 or later (the module uses standard WebAssembly exceptions). One process runs one job at a time, in
the order asked; several run side by side and share nothing. It ends when its input closes, or after a `close` job.

## Frames

Both ways, on the standard streams:

| Bytes | What |
|---|---|
| 8 | `N`, the length of the rest of the frame, unsigned, big-endian |
| 4 | `H`, the header's length, unsigned, big-endian |
| `H` | the header: one JSON object, UTF-8 |
| `N - 4 - H` | the payloads, end to end; the header's `payloads` lists their lengths in order |

A request's header is `{"id": ..., "job": NAME, ..., "payloads": [...]}`. Its answer carries the same `id` and either
`{"ok": true, ..., "payloads": [...]}` or `{"ok": false, "job": NAME, "error": TEXT}`. What the kernel refuses (bytes
that are no shape, an ordinal the part has not, a file that is no `.xbf`), a job this does not know and a frame it
cannot read are each an answer: the server goes on with the next frame. A frame longer than 2 GiB is passed over
as it comes and answered so.

## Jobs

Each answers what the engine's own job answers, in the engine's bytes: JSON is spelled as
`json.dumps(value, separators=(",", ":"))` spells it, a mesh is the XBM2 buffer of `Mesh.to_bytes()`.

| Job | Header, payloads | Answer | The engine's (`cad.engine`) |
|---|---|---|---|
| `about` | | `{abi, occt, memoryBytes}` | |
| `mesh` | `{tolerance?, angle?}`, a part's shape bytes | `{unmeshed: {ordinal: text}, seconds}`, the XBM2 buffer | `serve._timed`: `mesh_shape(data, tolerance=, angle=)`, its `to_bytes()` and `unmeshed` |
| `table` | `{key?, unmeshed: [ordinals], measure?}`, shape bytes | the table's JSON; then the measure's JSON where asked | `serve._table`: `Topology(data).elements(unmeshed)`, `.measured()` |
| `measured` | `{keys?}`, shape bytes of each part | each part's measure JSON, in order | `serve._measured` |
| `fact` | `{key?, method, args}`, shape bytes | the JSON | `serve._topology_fact`: `face`, `edge`, `vertex` (`args: [ordinal]`), `groups` (`[]`), `elements` (`[[ordinals]]`), `measured` (`[]`) |
| `read_xbf` | `{path}` | `{path, version: [mtime_ns as text, size], parts: [{key, name}...]}`, the structure's JSON, then each part's shape bytes in the parts' order | `serve._read_document` |
| `export` | `{path, format}` (`step`, `stl`, `threemf`, `glb`) | the file's bytes | `export.translate(path, kind, ...)` at the engine's own tessellation |
| `close` | | `{}`, and the process ends | |

- **A part's shape bytes** are `mesh.shape_bytes(shape, read=True)`: what `read_xbf` answers for each part, and what
  the engine keeps by the part's geometry key.
- **`key`** names the part for the jobs that follow: its topology is kept (the last 32 parts), as an engine pool
  process keeps it, so a table, its measure and a pick's facts read the shape once. Without it the part is opened
  for the job alone.
- **`read_xbf`'s structure** is the core's (`vc_structure`): the engine's `Loaded.structure()` once `path` and
  `version` (`"<mtime_ns>-<size>"`) are put in and `tessellation` and `closure`, which the server adds itself, are
  taken out. Colours are lists, as JSON has them, where the engine's own holds tuples. The file stays open for an
  `export` of it as it stood (the last 2 files): nothing is read twice.
- **An export's own tolerance** is the `mesh` job's (`tolerance` in millimetres, `angle` in degrees: the finer of
  each and the part's own, as `mesh_shape` takes them). The `export` job writes at the engine's tessellation only.
- **A face's fact** is a pick's: it says its checker's verdict. A table's row says it only for the faces named
  unmeshed.

`../../tools/pool_parity.py` holds every job against the engine's own code, part by part.

## Stills: the renderer this replaces, and what the core's must draw

cad draws a 3D still with OCCT's OpenGL viewer (`cad.engine.render`, `docs/viewer-and-snapshot.md` "The OCCT
stills"). A WebAssembly kernel has no OpenGL, so the core carries a rasterizer of its own (`src/render.cpp`,
`vc_render`, the `render` job below) that draws the same picture from the same inputs. This section is the contract
it is held to, read off the renderer it replaces.

### What Python hands OCCT

| Input | Where it comes from | How OCCT takes it |
|---|---|---|
| A part's mesh | the engine's XBM2 buffer (`Mesh.to_bytes()`): nodes with normals, triangles, the face table, edges as polylines with a class each | `shapes.py` crafts a triangulation-only shape per face group and a polygon shape per edge class; nothing is meshed by OCCT |
| An instance | its part, its 4x4 matrix (column-major, as the structure holds it) with the explode offset added to the translation, its colour or its part's | one connected presentation per part and look, placed |
| A face's material | `finish.finish(rgba, material)`: base colour (linear; a plain colour raised to the look's `colour_power` 2), alpha, metallic, roughness, IOR, emission. A painted face is a group of its own; Parts takes the palette's colour by `instance.palette` or index and keeps the part's opacity | a PHYSIC material, roughness as OCCT's normalized `(r - 0.01) / 0.99`; polygon offset (1, 1) when opaque, so edges win, (0, -4) when see-through |
| The light | `look.py`: one directional key (-0.35, 0.55, -1.0) at 4.0, white; the `studio.hdr` equirectangular radiance at 0.5 | PBR shading, the key a directional light, the image a cube map (256 a side, +Y up as OCCT reads it) OCCT bakes into nine spherical harmonics and six prefiltered levels |
| X-ray's light | `look.py`'s colour-only rig: ambient 0.5, two white directional lights, specular 0.08 at exponent 128 x 0.35 | Phong shading, the faces at opacity 0.22, the colour squared |
| The backdrop | `#f0f4f9`, or a job's own flat colour | a flat background |
| The camera | `Scene.frame`: a preset's or `azimuth:elevation`'s direction, then the tight orthographic frame of every placed vertex (the box's corners in Wireframe), or the perspective fit at three's 50 mm focal length; or a view's own camera | eye, target, up, and the view's height or its field of view (OCCT's scale and FOVy span the width of a picture taller than wide); near and far fitted to what is shown |
| The picture | width, height | an sRGB frame buffer, eight samples a pixel asked for |

### What changes a pixel

- **Display mode.** Solid: lit faces, visible edges. Shaded: lit faces. Parts: as Solid in the palette's colours.
  X-ray: colour-only faces at 0.22, every edge over them (a layer above, its depth its own). Hidden line: faces
  unlit in the backdrop's colour, visible edges. Wireframe: no faces, every edge. A robot (`kind` `urdf`, `srdf`)
  draws no edges in Solid and Parts.
- **Edges.** A part's polylines by class: feature (with boundary and non-manifold) `#253443`, tangent `#667788`,
  seam `#495b6c`, each a pixel wide, depth-tested against the faces stepped back by their polygon offset;
  `display.edges.classes` names the classes drawn.
- **Transparency.** Opaque faces first; then see-through ones in the order shown (instance by instance, group by
  group), depth-tested, writing no depth, blended source-over in linear light into the sRGB buffer. The PBR program
  scales the diffuse term by alpha and blends by `mix(1, alpha, 1 - F)`.
- **Clip.** One plane (`display.clip`: axis, `at`, `invert`) cutting every part; each instance's cut capped flat and
  unlit in its colour (linear, to the power 2; the palette's in Parts; `#e9a451` without `partColors`). No caps in
  Wireframe. The grid is never cut.
- **Grid.** `grid.py` computes the measuring grid on z = 0 for the framed camera as bands of triangles reading a
  profile texture (sRGB texels with alpha, bilinear), blended over the picture, depth-tested, stepped back as a face.
- **Hidden and isolated instances** are not shown, framed or capped.
- **Size.** Any width and height; antialiasing is the driver's multisampling (eight samples asked for, a
  software OpenGL gives four), resolved in linear light.

### What plain Python draws, before and after

Of `cad/engine/render` (6,660 lines): the look's numbers and environment (`look.py`), the scene's decisions
(`occt.py`'s `show`, `frame`, `placement`: which faces, which colour, which camera), the explode offsets
(`explode.py`), the clip plane and cap colours (`clip.py`'s `plane`, `cap_colour`), the grid's bands and texture
(`grid.py`), the annotation's ribbons and text quads (`occt.py`'s `annotate`, `text.py`), Measure's marks painted
over the frame (`overlay.py`), the PNG (`context.encode`) and the 2D drawings (`board.py`, `schematic.py`,
`drawing.py`) are plain Python and stay. What is OCCT's, and so the core's: the canvas and its context
(`context.py`), the shapes crafted for it (`shapes.py`), the materials and lights put up (`finish.py`'s `aspect`,
`put_up`), the presentations and the frame itself (`occt.py`), the cap carriers (`clip.py`'s `apply`), the grid's
and the ink's presentations (`grid._present`, `Scene._structure`).
