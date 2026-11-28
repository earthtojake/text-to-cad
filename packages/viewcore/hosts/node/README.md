# hosts/node (prototype)

The view core under Node: `viewcore.mjs` loads the module with the browser host's own loader and WASI shim, and
`serve.mjs` is a job server that answers the engine's pool jobs from it, in one long-lived process of a few tens of
megabytes.

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
| `render` | `{scene, keys?}`, the buffers the scene names, in order | `{width, height, format, seconds}`, the picture: RGBA bytes, or a PNG; or `{missing: [keys]}` and no picture | `render.occt`'s frame: `Scene.show`, `frame`, `grid`, `Canvas.frame` (below) |
| `forget` | `{keys?}` | `{kept, keptBytes}`: those kept buffers let go, or all | |
| `close` | | `{}`, and the process ends | |

- **`render`'s `keys`** keep a still's buffers in the server, so a part's mesh crosses the pipe once: `keys[i]`
  (a string, or null) names the buffer at place `i`. A buffer sent with a key is kept under it; one sent empty with a
  key is the one kept. Where a key names nothing kept (never sent, or let go: the server keeps the last 768 MiB of
  them, and none past `forget` or its end) the answer is `{missing: [keys]}`, and the caller sends the still again
  with those buffers. A mesh's key is its part's geometry key at its tessellation; the environment's any name of the
  image. Without `keys` every buffer is sent, as before.
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

### The scene

`render` (`vc_render`, `core.render(scene, payloads)`) takes the draw list Python made, in plain numbers. Lengths
are the model's (millimetres), colours linear RGB, matrices column-major as the structure holds them. A payload is
named by its place among the job's payloads.

| Member | What |
|---|---|
| `width`, `height` | the picture, in pixels |
| `samples` | samples a pixel: 1, 2, 4 or 8 (8, what cad asks of OpenGL; a software OpenGL gives 4) |
| `background` | the flat colour behind the model |
| `format` | `"rgba"` (width x height x 4 bytes, sRGB, the top row first), `"png"`, or `"depth"`: each pixel's depth (its first sample's), float32, 0 at the near plane to 1 at the far and where nothing is, the top row first (what `Scene._depth` reads of OCCT) |
| `camera` | `{projection: "orthographic" \| "perspective", eye, target, up, height \| fov}`: `height` the view's, `fov` the vertical field of view in degrees (`Scene.frame`'s record: `scale`, `fov`). Near and far are fitted to what is drawn, as `ZFitAll` fits them, unless `near` and `far` (distances along the view from the eye) are given |
| `light` | `{lights: [{direction, intensity, shadow?}...], environment: {payload, width, height, intensity, specularSize?, specularSamples?}}`: the PBR rig. `direction` is the way the light travels; the environment is the equirectangular radiance (`finish.environment()`: float32 RGB rows, +Z at the top). `shadow: {resolution, bias}` (the first light that has one): it casts a shadow on the faces as OCCT's shadow map does (`OpenGl_ShadowMap`: a square map `resolution` texels a side, orthographic along the light, Y up, 1.1 times the box of what is drawn; read with `LightShadow.glsl`'s sixteen taps and its bias rule). `specularSize` and `specularSamples` are the specular map's side as a power of two and its samples a texel (OCCT's `PbrEnvPow2Size` 9 and `PbrEnvBakingSpecNbSamples` 256 unless given; Preview bakes at 7 and 4096) |
| `phong` | `{ambient, specular, shininess, lights}`: X-ray's colour-only rig, in place of `light` |
| `clip` | `[a, b, c, d]`: what is kept is where `a x + b y + c z + d >= 0` |
| `backdrop` | `{payload, width, height}`: a picture behind everything in place of `background` (RGB bytes, sRGB, the top row first), stretched over the frame and read bilinearly in linear light at each pixel's centre, clamped at its edges |
| `meshes` | the payloads that are parts' XBM2 buffers; a draw names one by its place here |
| `matrices` | a payload of placements, sixteen float64 each; a draw's `matrix` is its place here (or sixteen numbers) |
| `draw` | what is drawn, in OCCT's order |

A draw is one of:

- `{faces: mesh, ranges?, matrix, shading, color, alpha, metallic, roughness, ior, emission, offset, texels?,
  texture?, layer}`: a part's triangles, all of them or the index ranges `[[first, count]...]` of a face group.
  `shading` is `"pbr"` (`finish.finish`'s numbers; `roughness` is three's), `"phong"` (`color` the part's colour,
  which the program squares) or `"unlit"`. `alpha` under 1 draws it after the opaque, blended, writing no depth.
  `offset` is the polygon offset `[factor, units]`. `texture: {payload, width, height}` with `texels` (a payload of
  two float32 a node of the mesh, its texture coordinates) is a base colour texture over `color` and `alpha` (a
  GLB's, `Scene._faces`' texture set): RGBA bytes, sRGB, rows from the top, v up, read bilinearly and repeated;
  F0 is worked out from the colour it gives. A texture drawn smaller than its texels (OCCT's mipmaps) is not.
- `{edges: mesh, classes, matrix, color, width, layer}`: the mesh's polylines of the classes named (the XBM2 edge
  table's codes), `width` pixels wide.
- `{lines: {positions, counts}, matrix?, color, width, clip, layer}`: polylines of the scene's own (a drawing's
  pens): their points end to end (float32 triples) and each one's count of them (uint32).
- `{cap: mesh, matrix, color}`: the instance's cut by `clip`, flat and unlit.
- `{triangles: {positions, texels?, colors?, indices}, texture?: {payload, width, height}, color, blend, offset,
  clip, infinite?, layer}`: triangles Python computed (the grid's bands, an annotation's ribbons and text, Preview's
  floor and its shadow), unlit, in `color` (RGBA) times the texture (RGBA bytes, sRGB, rows from the top, read
  bilinearly) or times the vertices' `colors` (RGBA bytes, each over 255 as OpenGL takes a vertex's colour, no sRGB
  curve; read across the triangle, and blended), blended where `blend`. `clip: false` leaves them uncut.
  `infinite: true` is a structure OCCT calls infinite: the planes are fitted to it whole, but the box that fits
  the perspective's near plane and the shadow map takes only its box's centre.

`layer` is `"default"`, `"top"` (above the model, tested against its depth, writing none: the ink) or `"topmost"`
(above everything, a depth of its own: X-ray's and Wireframe's edges). `tools/render_parity.py`'s `scene_of` builds
the scene from a `render.occt.Scene` shown and framed: the decisions of `Scene.show`, `clip.apply` and `grid.show`
without the OCCT calls.

### How it is held to OpenGL's picture

`tools/render_parity.py reference` draws a set of cases with cad's renderer and writes each one's scene;
`compare` draws them with the core and measures the two pictures apart. What the rasterizer reproduces, each found
by that measure: OpenGL's sample positions and fill rule run up the picture (the frame is stored bottom row first);
a line is the rectangle a pixel wide about it; the frame is resolved in linear light from sRGB bytes; a see-through
surface is blended in the order drawn; a cap passes the depth only where it is nearer. Of OCCT's PBR program: a
face seen from behind is lit by its lights with the normal turned over and by the environment with the normal as it
is; the view direction is a vertex's, read across the triangle; the environment's cube map is read by the nearest
texel (cad sets no filter on it); the specular map is kept in bytes, of the cube map's 0 to 1. A lit face's
pixels are lit four at a time (128-bit SIMD), each lane the arithmetic of one pixel in the same order, so the bytes
are the same lit either way.

Preview (`Scene.preview_look`) is drawn by cad's own Preview code with the core under it: `render_parity.py
preview` runs `Scene._studio`, `_studio_backdrop` and `painter` with the scene's canvas, `_depth` and `_structure`
swapped for the core's (a frame is the model as `scene_of` says it, the studio's floor and shadow as `triangles`,
the backdrop picture; a depth is a `"depth"` frame through the 8-bit picture OCCT dumps a depth into). What OCCT
does there and the core is told: the background picture shows its last row all the way down; a square depth
picture is drawn with the view's own aspect.

`render_parity.py ink` holds an annotation's ink (`Scene.annotate`: a stroke's ribbon read back off the shape
shown, a thin one as a polyline, a text mark's quad with its words' picture) in the `top` layer against today's, and
`render_parity.py drawing` a DXF drawn whole (`drawing.Held`: each pen's fills and lines, one sample a pixel)
against today's; the words painted over a frame in Python are the same over either and left out of both.

Not drawn by the core: the path tracer.
