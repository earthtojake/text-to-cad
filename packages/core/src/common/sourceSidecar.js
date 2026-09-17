// Saved STEP declarations are document-bound data. Geometry remains identified
// by the immutable STEP tree; these helpers validate declarations and compose
// appearance into private descriptors owned by the current reader/session.

export const SOURCE_SIDECAR_SCHEMA_VERSION = 9;
export const SOURCE_APPEARANCE_CHANNELS = Object.freeze([
  "baseColor",
  "roughness",
  "metalness",
  "clearcoat",
  "clearcoatRoughness",
  "opacity"
]);
export const SOURCE_MATERIAL_DEFAULTS = Object.freeze({
  roughness: 0.42,
  metalness: 0.03,
  clearcoat: 0,
  clearcoatRoughness: 0.26,
  opacity: 1
});

const NUMERIC_MATERIAL_CHANNELS = SOURCE_APPEARANCE_CHANNELS.filter((key) => key !== "baseColor");
const MATERIAL_KEYS = new Set(["name", ...SOURCE_APPEARANCE_CHANNELS]);
const SIDECAR_KEYS = new Set(["schemaVersion", "documentHash", "kinematics", "appearance", "animation"]);

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function sidecarName(url) {
  const text = String(url || "").split("#")[0];
  const query = /[?&]file=([^&]+)/.exec(text);
  const target = query ? decodeURIComponent(query[1]) : text.split("?")[0];
  return target.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "sidecar";
}

function normalizedDocumentHash(value) {
  const digest = String(value || "").trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(digest) ? digest : "";
}

function nonemptyString(value, where) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${where} must be a nonempty string`);
  }
  return value.trim();
}

function normalizeMaterial(value, materialId, { nameRequired = true } = {}) {
  const keys = isObject(value) ? Object.keys(value) : [];
  if (!isObject(value) || keys.some((key) => !MATERIAL_KEYS.has(key))) {
    throw new Error(
      `material ${JSON.stringify(materialId)} must contain only name, ${SOURCE_APPEARANCE_CHANNELS.join(", ")}`
    );
  }
  const normalized = {};
  if (Object.hasOwn(value, "name")) {
    normalized.name = nonemptyString(value.name, `material ${JSON.stringify(materialId)}.name`);
  } else if (nameRequired) {
    throw new Error(`material ${JSON.stringify(materialId)}.name must be a nonempty string`);
  }
  if (Object.hasOwn(value, "baseColor")) {
    const color = String(value.baseColor || "");
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) {
      throw new Error(`material ${JSON.stringify(materialId)}.baseColor must be a #RRGGBB color`);
    }
    normalized.baseColor = color.toUpperCase();
  }
  for (const key of NUMERIC_MATERIAL_CHANNELS) {
    if (!Object.hasOwn(value, key)) continue;
    const channel = value[key];
    if (typeof channel !== "number" || !Number.isFinite(channel) || channel < 0 || channel > 1) {
      throw new Error(
        `material ${JSON.stringify(materialId)}.${key} must be a finite number between 0 and 1`
      );
    }
    normalized[key] = channel;
  }
  return normalized;
}

function normalizeAppearanceShape(block, {
  label = "appearance",
  allowPartialMaterials = false,
  allowUnknownAssignments = false
} = {}) {
  if (block === undefined || block === null) return null;
  if (!isObject(block) || Object.keys(block).length !== 2
    || !Object.hasOwn(block, "materials") || !Object.hasOwn(block, "assignments")) {
    throw new Error(`${label} must contain only materials and assignments objects`);
  }
  if (!isObject(block.materials) || !isObject(block.assignments)) {
    throw new Error(`${label}.materials and ${label}.assignments must be objects`);
  }
  const materials = {};
  for (const rawMaterialId of Object.keys(block.materials).sort()) {
    const materialId = nonemptyString(rawMaterialId, `${label} material id`);
    materials[materialId] = normalizeMaterial(block.materials[rawMaterialId], materialId, {
      nameRequired: !allowPartialMaterials
    });
  }
  const assignments = {};
  for (const rawOccurrenceId of Object.keys(block.assignments).sort()) {
    const occurrenceId = nonemptyString(rawOccurrenceId, `${label} assignment occurrence id`);
    const materialId = nonemptyString(
      block.assignments[rawOccurrenceId],
      `${label} assignment ${occurrenceId}`
    );
    if (!allowUnknownAssignments && !Object.hasOwn(materials, materialId)) {
      throw new Error(`${label} assignment ${occurrenceId} references unknown material ${JSON.stringify(materialId)}`);
    }
    assignments[occurrenceId] = materialId;
  }
  return Object.keys(materials).length || Object.keys(assignments).length ? { materials, assignments } : null;
}

export function normalizeSourceAppearance(block) {
  return normalizeAppearanceShape(block);
}

// A session overlay uses the saved shape but may patch an existing material,
// add a named material for duplication, and redirect leaf assignments. The
// returned effective appearance owns every row and never mutates saved data.
export function resolveSourceAppearance(baseAppearance, sessionOverlay = null) {
  const base = normalizeSourceAppearance(baseAppearance);
  if (sessionOverlay === undefined || sessionOverlay === null) return base;
  const overlay = normalizeAppearanceShape(sessionOverlay, {
    label: "appearance session overlay",
    allowPartialMaterials: true,
    allowUnknownAssignments: true
  });
  const materials = Object.fromEntries(
    Object.entries(base?.materials || {}).map(([materialId, material]) => [materialId, { ...material }])
  );
  for (const [materialId, patch] of Object.entries(overlay?.materials || {})) {
    const existing = materials[materialId];
    if (!existing && !Object.hasOwn(patch, "name")) {
      throw new Error(`new session material ${JSON.stringify(materialId)} requires a nonempty name`);
    }
    materials[materialId] = { ...(existing || {}), ...patch };
  }
  const assignments = { ...(base?.assignments || {}), ...(overlay?.assignments || {}) };
  for (const [occurrenceId, materialId] of Object.entries(assignments)) {
    if (!Object.hasOwn(materials, materialId)) {
      throw new Error(
        `appearance session assignment ${occurrenceId} references unknown material ${JSON.stringify(materialId)}`
      );
    }
  }
  return Object.keys(materials).length || Object.keys(assignments).length ? { materials, assignments } : null;
}

export function sourceMaterialForOccurrence(appearance, occurrenceId, sessionOverlay = null) {
  const resolved = resolveSourceAppearance(appearance, sessionOverlay);
  const id = String(occurrenceId || "").trim();
  const materialId = resolved?.assignments?.[id];
  const material = materialId ? resolved.materials[materialId] : null;
  return material ? { materialId, ...SOURCE_MATERIAL_DEFAULTS, ...material } : null;
}

export function normalizeSourceAnimation(block) {
  if (block === undefined || block === null) return null;
  if (!isObject(block) || Object.keys(block).length !== 2
    || !Object.hasOwn(block, "language") || !Object.hasOwn(block, "source")) {
    throw new Error("animation must contain only language and source");
  }
  if (block.language !== "javascript") {
    throw new Error("animation.language must be 'javascript'");
  }
  if (typeof block.source !== "string" || !block.source.trim()) {
    throw new Error("animation.source must be a nonempty JavaScript module");
  }
  return { language: "javascript", source: block.source };
}

export function validateSourceSidecar(sidecar, { url = "", documentHash = "" } = {}) {
  if (!isObject(sidecar)) {
    throw new Error(`${sidecarName(url)}: unsupported sidecar schema none (expected ${SOURCE_SIDECAR_SCHEMA_VERSION})`);
  }
  if (sidecar.schemaVersion !== SOURCE_SIDECAR_SCHEMA_VERSION) {
    const name = sidecarName(url);
    const model = name.replace(/\.(step|stp)\.json$/i, "");
    throw new Error(
      `${name}: unsupported sidecar schema ${sidecar.schemaVersion ?? "none"} `
      + `(expected ${SOURCE_SIDECAR_SCHEMA_VERSION}) — rebuild the model `
      + `(python ${model}.py) or re-annotate the document (cadgen step build)`
    );
  }
  const unknown = Object.keys(sidecar).filter((key) => !SIDECAR_KEYS.has(key));
  if (unknown.length) {
    throw new Error(`${sidecarName(url)}: unknown sidecar field${unknown.length === 1 ? "" : "s"} ${unknown.join(", ")}`);
  }
  const expected = normalizedDocumentHash(documentHash);
  if (!expected) {
    throw new Error(`${sidecarName(url)}: saved sidecar load requires the STEP documentHash`);
  }
  const found = normalizedDocumentHash(sidecar.documentHash);
  if (found !== expected) {
    const name = sidecarName(url);
    const model = name.replace(/\.(step|stp)\.json$/i, "");
    throw new Error(
      `${name}: documentHash ${found || "none"} does not match STEP sha256 ${expected} `
      + `— rebuild the model (python ${model}.py) or re-annotate the document (cadgen step build)`
    );
  }
  return {
    ...sidecar,
    ...(Object.hasOwn(sidecar, "appearance")
      ? { appearance: normalizeSourceAppearance(sidecar.appearance) }
      : {}),
    ...(Object.hasOwn(sidecar, "animation")
      ? { animation: normalizeSourceAnimation(sidecar.animation) }
      : {})
  };
}

export async function loadSourceSidecar(sidecarUrl, { documentHash = "", signal, resources, fetch: fetchImpl = globalThis.fetch } = {}) {
  signal?.throwIfAborted();
  const url = String(sidecarUrl || "").trim();
  if (!url) return null;
  if (resources) {
    const sidecar = await resources.readJson(url, { signal });
    signal?.throwIfAborted();
    return validateSourceSidecar(sidecar, { url, documentHash });
  }
  const response = await fetchImpl(url, { cache: "no-store", signal });
  signal?.throwIfAborted();
  if (!response.ok) {
    throw new Error(`Failed to load model sidecar: HTTP ${response.status}`);
  }
  const sidecar = await response.json();
  signal?.throwIfAborted();
  return validateSourceSidecar(sidecar, { url, documentHash });
}

export function applySourceAppearance(descriptor, block, { sessionOverlay = null } = {}) {
  if (!isObject(descriptor)) {
    throw new Error("appearance requires an assembly package descriptor");
  }
  const appearance = resolveSourceAppearance(block, sessionOverlay);
  if (!appearance) return descriptor;
  const sourceOccurrences = Array.isArray(descriptor.occurrences) ? descriptor.occurrences : [];
  const byId = new Map(sourceOccurrences.map((occurrence) => [String(occurrence?.id || ""), occurrence]));
  const replacements = new Map();
  for (const [occurrenceId, materialId] of Object.entries(appearance.assignments)) {
    const target = byId.get(occurrenceId);
    if (!target || !String(target.component || "").trim()) {
      throw new Error(`appearance targets missing document occurrence ${occurrenceId}`);
    }
    const authored = appearance.materials[materialId];
    const { name: materialName, baseColor, ...channels } = authored;
    replacements.set(occurrenceId, {
      ...target,
      materialId,
      materialName,
      material: { ...SOURCE_MATERIAL_DEFAULTS, ...channels },
      ...(baseColor ? { baseColor } : {})
    });
  }
  return {
    ...descriptor,
    appearance,
    occurrences: sourceOccurrences.map((occurrence) => (
      replacements.get(String(occurrence?.id || "")) || occurrence
    ))
  };
}
