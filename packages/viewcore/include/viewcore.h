/* viewcore.h: the view core's C ABI, version 1 (prototype).
 *
 * One WebAssembly module (wasm32, standalone: it imports WASI alone) that reads a model's .xbf and answers what
 * the viewer reads of it, by cad's own rules. The rules are cad's Python, which stays the reference until this
 * replaces it: packages/cad/src/cad/engine/mesh.py (shape bytes, meshing, the XBM2 buffer, element facts, groups,
 * measures), mesh_format.py (the buffer's layout), document.py (reading an .xbf: parts, keys, names, placements),
 * kernel/bounds.py (boxes). The same file runs in a page (a Worker) and in the engine (wasmtime).
 *
 * Memory. The host hands the core bytes in a buffer it takes with vc_alloc and gives back with vc_free. Every
 * result is a buffer the core allocated: the pointer is returned, its length written to *out_len, and the host
 * frees it with vc_free. A NULL result (or a 0 handle) is an error: vc_last_error() says why (NUL-terminated,
 * valid until the next call). JSON is UTF-8, compact, numbers as the shortest text that reads back as the same
 * double.
 *
 * Parts and ordinals. A part is a prototype of the document, numbered as document.Loaded.prototypes numbers them
 * (0-based "index"). An element ordinal is 1-based: the part's TopExp::MapShapes ordinal of that kind, as cad's.
 */
#ifndef VIEWCORE_H
#define VIEWCORE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VC_ABI_VERSION 4u

enum { VC_FACE = 0, VC_EDGE = 1, VC_VERTEX = 2 };

uint32_t vc_abi_version(void);
/* The OCCT release linked in, e.g. "8.0.1" (static text). */
const char *vc_occt_version(void);
const char *vc_last_error(void);

void *vc_alloc(uint32_t size);
void vc_free(void *ptr);

/* Read an .xbf (BinXCAF) from memory: a handle > 0, or 0. `stem` (UTF-8, `stem_len` bytes; NULL or empty for
 * "document") is what document.Loaded names the document by where its file does not: the file's stem, for an
 * unnamed root or a file of several roots. */
int32_t vc_open_xbf(const uint8_t *data, uint32_t size, const char *stem, uint32_t stem_len);
/* A part's canonical shape bytes (mesh.shape_bytes, what vc_shape_bytes answers) opened by themselves, as the
 * engine's pool jobs hand a part over: a handle > 0, or 0, of one part, index 0. It answers vc_shape_bytes (the bytes
 * as given), vc_mesh, vc_mesh_at, vc_unmeshed, vc_fact, vc_groups, vc_table, vc_elements and vc_measure; it has no
 * structure and no exports. */
int32_t vc_open_shape(const uint8_t *data, uint32_t size);
void vc_close(int32_t doc);

/* The document's structure, JSON, as document.Loaded.structure() writes it, with the build closure its file holds
 * (`closure`, null for none; serve._closed) and the tessellation every part is meshed at (`tessellation`): {"name",
 * "units", "tessellation", "prototypes": [{"index", "key", "name", "color", "faceNames", "edgeNames", "vertexNames",
 * "faceColors", "material", "faceMaterials", "frames", and what the part declares ("body", "drives", "mass",
 * "pointMasses", "free", "link"), "untextured" where its materials carry texture maps}...], "instances": [{"prototype",
 * "path", "matrix", "color"}...], "tree", "kinematics" (mechanism.block, where the document holds a mechanism),
 * "animations" and "parameters" (where it holds any), "closure"}. Not given: where the document lives ("path",
 * "version", "id": the host's). "key" is the geometry key the file holds for the part. A material is the record cad
 * wrote beside XCAF's (a file cad did not write gives none). */
uint8_t *vc_structure(int32_t doc, uint32_t *out_len);

/* A part's canonical shape bytes: mesh.shape_bytes(shape, read=True) (BinTools format 4, geometry only, at the
 * identity, bookkeeping flags settled). blake2b-128 of them is the part's geometry key. */
uint8_t *vc_shape_bytes(int32_t doc, int32_t part, uint32_t *out_len);

/* A part's mesh: the XBM2 buffer of mesh_format.Mesh.to_bytes for mesh.mesh_shape(shape_bytes) at cad's
 * tessellation (DEVIATION, ANGULAR), meshed from a fresh shape read from the canonical bytes, one thread. */
uint8_t *vc_mesh(int32_t doc, int32_t part, uint32_t *out_len);

/* A part meshed to an export's own ceilings: mesh.mesh_shape(shape_bytes, tolerance=, angle=), `tolerance` the linear
 * deflection's in millimetres and `angle` the angular's in degrees, each the finer of itself and the part's own; a
 * value <= 0 gives none. Not kept: vc_mesh, the exports and vc_elements stay at cad's one tessellation. */
uint8_t *vc_mesh_at(int32_t doc, int32_t part, double tolerance, double angle, uint32_t *out_len);

/* The faces the part's last mesh (vc_mesh or vc_mesh_at) left without triangles, JSON: mesh_shape(...).unmeshed, each
 * ordinal with what the mesher and the checker say of it ({"7": "BRepMesh: no status; BRepCheck: valid"}); {} for
 * none, and for a part not meshed yet. */
uint8_t *vc_unmeshed(int32_t doc, int32_t part, uint32_t *out_len);

/* One element's facts, JSON: mesh.Topology(bytes).face/edge/vertex(ordinal). What a pick asks. */
uint8_t *vc_fact(int32_t doc, int32_t part, int32_t kind, int32_t ordinal, uint32_t *out_len);

/* A part's groups, JSON: mesh.Topology(bytes).groups() (each face's tangent group, each edge's chain). */
uint8_t *vc_groups(int32_t doc, int32_t part, uint32_t *out_len);

/* A part's whole table, JSON: mesh.Topology(bytes).elements(). What a view bundle holds; a page asks per pick. */
uint8_t *vc_elements(int32_t doc, int32_t part, uint32_t *out_len);

/* A part's whole table with the caller's unmeshed faces checked, JSON: mesh.Topology(bytes).elements(unmeshed), the
 * `count` ordinals at `unmeshed` those of the faces its mesh left without triangles (the engine keeps them with the
 * mesh). vc_elements is this with the ordinals of the part's own vc_mesh. */
uint8_t *vc_table(int32_t doc, int32_t part, const int32_t *unmeshed, uint32_t count, uint32_t *out_len);

/* A part measured as a whole, JSON: mesh.measured(bytes). */
uint8_t *vc_measure(int32_t doc, int32_t part, uint32_t *out_len);

/* Exports: a file of the whole document, as `cad export FILE.xbf OUT` writes it (cad/engine/export). */

/* The document's STEP (AP242), export/step.py's bytes: names, colours, materials and element names; a pinned time
 * stamp, so the same document writes the same bytes. */
uint8_t *vc_step(int32_t doc, uint32_t *out_len);

/* The document's binary STL, export/stl.py's bytes: every placed triangle at cad's tessellation, in millimetres. */
uint8_t *vc_stl(int32_t doc, uint32_t *out_len);

/* The document's 3MF, export/threemf.py's: an object per part (its vertices welded), a build item per placement, its
 * looks as base materials, in a zip deflated by zlib. */
uint8_t *vc_3mf(int32_t doc, uint32_t *out_len);

/* The document's GLB, export/glb.py's: a mesh per part, its looks as glTF materials, the assembly as nodes, every
 * configuration sequence and animation as a glTF animation. */
uint8_t *vc_glb(int32_t doc, uint32_t *out_len);

/* A still, drawn in software (src/render.cpp): the picture cad's OpenGL renderer draws from the same inputs. `scene`
 * is JSON (UTF-8, `scene_len` bytes) and `blob` its payloads end to end, their lengths the scene's "payloads"; no
 * document is opened and nothing is meshed. The scene (hosts/node/README.md, "Stills", says each member):
 *   {"width", "height", "samples" (1, 2, 4 or 8; 8), "background": [r, g, b], "format" ("rgba", or "png"),
 *    "camera": {"projection" ("orthographic" | "perspective"), "eye", "target", "up", "height" | "fov"},
 *    "light": {"lights": [{"direction", "intensity"}...], "environment": {"payload", "width", "height", "intensity"}}
 *      or "phong": {"ambient", "specular", "shininess", "lights"},
 *    "clip": [a, b, c, d], "payloads": [length...], "meshes": [payload...],
 *    "draw": [{"faces": mesh, "ranges", "matrix", "shading", "color", "alpha", "metallic", "roughness", "ior",
 *              "emission", "offset", "layer"} | {"edges": mesh, "classes", "matrix", "color", "width", "layer"} |
 *             {"cap": mesh, "matrix", "color"} | {"triangles": {"positions", "texels", "indices"}, "texture",
 *              "color", "blend", "offset", "clip", "layer"}...]}
 * A mesh is a part's XBM2 buffer (vc_mesh); colours are linear. The result is width x height RGBA bytes, sRGB, the
 * top row first, or a PNG of them. The same scene gives the same bytes wherever the module runs. */
uint8_t *vc_render(const char *scene, uint32_t scene_len, const uint8_t *blob, uint32_t blob_len, uint32_t *out_len);

#ifdef __cplusplus
}
#endif

#endif
