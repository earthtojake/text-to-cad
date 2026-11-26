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

#define VC_ABI_VERSION 1u

enum { VC_FACE = 0, VC_EDGE = 1, VC_VERTEX = 2 };

uint32_t vc_abi_version(void);
/* The OCCT release linked in, e.g. "8.0.1" (static text). */
const char *vc_occt_version(void);
const char *vc_last_error(void);

void *vc_alloc(uint32_t size);
void vc_free(void *ptr);

/* Read an .xbf (BinXCAF) from memory: a handle > 0, or 0. */
int32_t vc_open_xbf(const uint8_t *data, uint32_t size);
void vc_close(int32_t doc);

/* The document's structure, JSON, by document.Loaded.structure's names: {"prototypes": [{"index", "key", "name",
 * "color", "faceNames", "edgeNames", "vertexNames", "faceColors"}...], "instances": [{"prototype", "path",
 * "matrix", "color"}...]}. "key" is the geometry key the file holds for the part. (Materials, frames, the tree,
 * kinematics, animations and parameters: later versions.) */
uint8_t *vc_structure(int32_t doc, uint32_t *out_len);

/* A part's canonical shape bytes: mesh.shape_bytes(shape, read=True) (BinTools format 4, geometry only, at the
 * identity, bookkeeping flags settled). blake2b-128 of them is the part's geometry key. */
uint8_t *vc_shape_bytes(int32_t doc, int32_t part, uint32_t *out_len);

/* A part's mesh: the XBM2 buffer of mesh_format.Mesh.to_bytes for mesh.mesh_shape(shape_bytes) at cad's
 * tessellation (DEVIATION, ANGULAR), meshed from a fresh shape read from the canonical bytes, one thread. */
uint8_t *vc_mesh(int32_t doc, int32_t part, uint32_t *out_len);

/* One element's facts, JSON: mesh.Topology(bytes).face/edge/vertex(ordinal). What a pick asks. */
uint8_t *vc_fact(int32_t doc, int32_t part, int32_t kind, int32_t ordinal, uint32_t *out_len);

/* A part's groups, JSON: mesh.Topology(bytes).groups() (each face's tangent group, each edge's chain). */
uint8_t *vc_groups(int32_t doc, int32_t part, uint32_t *out_len);

/* A part's whole table, JSON: mesh.Topology(bytes).elements(). What a view bundle holds; a page asks per pick. */
uint8_t *vc_elements(int32_t doc, int32_t part, uint32_t *out_len);

/* A part measured as a whole, JSON: mesh.measured(bytes). */
uint8_t *vc_measure(int32_t doc, int32_t part, uint32_t *out_len);

#ifdef __cplusplus
}
#endif

#endif
