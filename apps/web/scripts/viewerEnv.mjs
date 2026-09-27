export const DEPRECATED_LOCAL_ROOT_ENV_VARS = Object.freeze([
  "VIEWER_LOCAL_ROOT_DIR",
  "VIEWER_LOCAL_WORKSPACE_ROOT",
]);

export function assertNoDeprecatedLocalRootEnv(env = process.env) {
  const configured = DEPRECATED_LOCAL_ROOT_ENV_VARS.filter((name) => String(env?.[name] || "").trim());
  if (configured.length) {
    throw new Error(
      `${configured.join(", ")} ${configured.length === 1 ? "is" : "are"} no longer supported. ` +
      "Start dev from the directory to serve with npm --prefix <checkout>/apps/web run dev. " +
      "Open the bare origin with ?file=<relative-path> to select an artifact within that root."
    );
  }
}
