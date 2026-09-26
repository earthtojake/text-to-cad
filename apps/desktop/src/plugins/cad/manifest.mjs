/**
 * What the CAD plugin adds to the base app: the CAD Viewer for STEP, meshes, robots and drawings,
 * the agent tools that drive it, and the repository's CAD skills. Plain data: main, the renderer
 * and the build read it.
 */
export default /** @type {const} */ ({
  id: "cad",
  name: "CAD",
  description: "The CAD Viewer for STEP, meshes, robot descriptions and DXF drawings, the tools that let the agent drive it, and the CAD skills.",
  // The nine extensions the CAD Viewer's file surface understands.
  fileTypes: [
    { kind: "cad", mime: "model/step", extensions: ["step", "stp"] },
    { kind: "cad", mime: "model/gltf-binary", extensions: ["glb"] },
    { kind: "cad", mime: "model/stl", extensions: ["stl"] },
    { kind: "cad", mime: "model/3mf", extensions: ["3mf"] },
    { kind: "cad", mime: "image/vnd.dxf", extensions: ["dxf"] },
    { kind: "cad", mime: "application/xml", extensions: ["urdf", "srdf", "sdf"] },
  ],
  skills: ["skills/cad-viewer"],
  repoSkills: ["cad", "step-parts", "dxf", "engineering-drawing", "urdf", "srdf", "sdf", "dfm", "dfam-check", "sendcutsend", "bambu-labs"],
  commands: {
    viewer_state: "viewer-state", select_reference: "select-reference", capture_view: "capture-view",
    clear_selection: "cad-clear-selection", set_camera: "cad-camera", reset_camera: "cad-reset-camera", set_render_mode: "cad-render-mode",
  },
});
