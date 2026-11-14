import { createToolModes } from "../kit/tools/toolModes.js";

// A field's one tool: Select, the view's plain navigation. It picks nothing: a field has no faces or
// parts a press could name, and a Quick Edit names the whole file.
export const FIELD_TOOL = Object.freeze({ SELECT: "select" });

export const FIELD_TOOL_MODES = createToolModes({ defaultMode: FIELD_TOOL.SELECT, modes: { [FIELD_TOOL.SELECT]: {} } });

/** What a host command a field cannot carry out is told. */
export const FIELD_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GSL model is a field with no references a command can select: it is named as the whole file. Control the camera and display settings instead."
});
