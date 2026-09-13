// Source-backed assemblies regenerate the canonical STEP, rebuild topology,
// inspect it, and validate it. Keep the wire deadline slightly above the
// host-side 120-second CAD tool limit so the renderer receives the real result.
export const CAD_VALIDATION_WIRE_TIMEOUT_MS = 150_000;
