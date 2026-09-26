/** What the G-code plugin adds: a toolpath viewer for sliced prints, beside the repo's `gcode` skill. */
export default /** @type {const} */ ({
  id: "gcode",
  name: "G-code",
  description: "Toolpath viewing for sliced G-code, with its layers, extents and moves for the agent.",
  fileTypes: [{ kind: "text", mime: "text/x-gcode", extensions: ["gcode", "gco", "ngc"] }],
  skills: [],
  repoSkills: ["gcode"],
  commands: { gcode_state: "gcode-state", set_gcode_layer: "gcode-layer", capture_gcode: "gcode-capture" },
});
