// The one JS GLB writer lives in implicitjs as the single source of truth; cadjs depends on
// implicitjs and re-exports it here, the same arrangement as `cadjs/common/camera.js`.
// Consumers (the CAD Viewer, the artifact builders) install and import cadjs alone rather
// than depending on implicitjs directly or keeping a second serializer.
export * from "implicitjs/glb/writeGlb.js";
