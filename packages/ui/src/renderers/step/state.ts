// What a HOST needs of the STEP renderer's stored state, and nothing more: the orbit
// preference, which is a preference rather than per-file state. The per-file record itself
// is the shell's (`kit/shell/shellState.js`) and a host treats it as opaque JSON; the width
// of the panel column is the shared column's (`@hardcore/ui/navigation`).
export { ORBIT_STORAGE_KEY, readOrbit, writeOrbit, normalizeOrbit } from "../kit/tools/fullscreen/orbitPreferences.js";
