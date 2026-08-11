// Camera preset/spec resolution lives in implicitjs as the single source of
// truth. cadjs depends on implicitjs and re-exports it here so existing
// `cadjs/common/camera.js` importers keep working without maintaining a second
// byte-identical copy.
export * from "implicitjs/common/camera.js";
