import {
  resolveSourceAppearance,
  SOURCE_MATERIAL_DEFAULTS
} from "@hardcore/core/common/sourceSidecar.js";

const EMPTY_OVERLAY = Object.freeze({ materials: Object.freeze({}), assignments: Object.freeze({}) });
// Appearance wrappers share geometry; retain its identity for LOD ownership
// acknowledgments, including delayed teardown of an older display wrapper.
const materialGeometrySources = new WeakMap();
export function sourceMaterialGeometry(display) {
  return materialGeometrySources.get(display) || display;
}

export const MATERIAL_FINISH_PRESETS = Object.freeze([
  { id: "matte-plastic", name: "Matte plastic", roughness: 0.75, metalness: 0, clearcoat: 0, clearcoatRoughness: 0.2 },
  { id: "glossy-plastic", name: "Glossy plastic", roughness: 0.2, metalness: 0, clearcoat: 0.8, clearcoatRoughness: 0.1 },
  { id: "rubber", name: "Rubber", roughness: 0.95, metalness: 0, clearcoat: 0, clearcoatRoughness: 0.2 },
  { id: "satin-metal", name: "Satin metal", roughness: 0.35, metalness: 1, clearcoat: 0, clearcoatRoughness: 0.2 },
  { id: "polished-metal", name: "Polished metal", roughness: 0.08, metalness: 1, clearcoat: 0, clearcoatRoughness: 0.2 },
  { id: "ceramic", name: "Glazed ceramic", roughness: 0.2, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.12 }
].map(Object.freeze));
const FINISH_CHANNELS = ["roughness", "metalness", "clearcoat", "clearcoatRoughness"];

export function materialForSelection(appearance, ids) {
  const materials = new Set(ids.map(id => appearance?.assignments?.[id] || ""));
  if (materials.size > 1) return { materialId: "", label: "Mixed" };
  const materialId = [...materials][0] || "";
  return { materialId, label: appearance?.materials?.[materialId]?.name || "Unassigned" };
}

export function applyMaterialChoice(appearance, overlay, ids, choice) {
  if (!ids.length) return null;
  if (choice.startsWith("preset:")) {
    const added = addSourceMaterialPreset(appearance, overlay, choice.slice(7));
    return added ? { ...added, overlay: assignSourceMaterialOverlay(added.overlay, ids, added.materialId) } : null;
  }
  const materialId = choice.startsWith("material:") ? choice.slice(9) : "";
  if (!effectiveSourceAppearance(appearance, overlay)?.materials?.[materialId]) return null;
  return { materialId, overlay: assignSourceMaterialOverlay(overlay, ids, materialId) };
}

function applySourceMaterialPreset(overlay, materialId, presetId) {
  const preset = MATERIAL_FINISH_PRESETS.find(item => item.id === presetId);
  if (!preset) return sessionOverlay(overlay);
  return patchSourceMaterialOverlay(overlay, materialId,
    Object.fromEntries(FINISH_CHANNELS.map(key => [key, preset[key]])));
}

function addSourceMaterialPreset(appearance, overlay, presetId) {
  const preset = MATERIAL_FINISH_PRESETS.find(item => item.id === presetId);
  if (!preset) return null;
  const ids = new Set(Object.keys(effectiveSourceAppearance(appearance, overlay)?.materials || {}));
  let materialId = preset.id, index = 2;
  while (ids.has(materialId)) materialId = `${preset.id}-${index++}`;
  const named = patchSourceMaterialOverlay(overlay, materialId, { name: index > 2 ? `${preset.name} ${index - 1}` : preset.name, opacity: 1 });
  return { materialId, overlay: applySourceMaterialPreset(named, materialId, presetId) };
}

function normalizedId(value) {
  return String(value || "").trim();
}

function sessionOverlay(value) {
  return value && typeof value === "object"
    ? {
        materials: value.materials && typeof value.materials === "object" ? value.materials : {},
        assignments: value.assignments && typeof value.assignments === "object" ? value.assignments : {}
      }
    : EMPTY_OVERLAY;
}

export function sourceMaterialOverlayIsEmpty(value) {
  const overlay = sessionOverlay(value);
  return !Object.keys(overlay.materials).length && !Object.keys(overlay.assignments).length;
}

export function sourceAppearanceHasMaterials(appearance) {
  const resolved = resolveSourceAppearance(appearance);
  return Boolean(resolved && Object.keys(resolved.materials || {}).length);
}

// The one rule for whether the Materials tab exists: every STEP can be given
// materials in-session, and any other format that already ships named ones can
// be retouched. It decides both the tab strip entry and the tab itself, so the
// two can never disagree about whether the panel is there.
export function sourceMaterialsPanelEnabled(fileSheetKind, appearance) {
  return String(fileSheetKind || "") === "step" || sourceAppearanceHasMaterials(appearance);
}

export function effectiveSourceAppearance(appearance, overlay) {
  return resolveSourceAppearance(appearance, sessionOverlay(overlay));
}

function sourceMaterialParts(meshData) {
  return (Array.isArray(meshData?.parts) ? meshData.parts : []).map((part) => ({
    id: normalizedId(part?.occurrenceId || part?.id),
    label: String(part?.label || part?.name || part?.occurrenceId || part?.id || "Part").trim() || "Part",
    color: String(part?.sourceColor || "").trim()
  })).filter((part) => part.id);
}

// A STEP occurrence with no authored name arrives carrying the exchange file's
// placeholder (`=>[...]`), which is not a name to show anyone. A lone unnamed
// body is the model, so it takes the model's file name; several unnamed bodies
// become ordinals. Resolved here so every consumer gets a label it can render.
const PLACEHOLDER_PART_LABEL = /^=>\[/u;

function displayPartLabel(part, index, partCount, scope) {
  if (!PLACEHOLDER_PART_LABEL.test(part.label)) return part.label;
  const modelName = partCount === 1
    ? String(scope || "").split("/").pop().replace(/\.step$/iu, "")
    : "";
  return modelName || `Part ${index + 1}`;
}

export function sourceMaterialTargets(meshData, scope = "") {
  const parts = sourceMaterialParts(meshData);
  const partById = new Map(parts.map((part) => [part.id, part]));
  const targets = [];
  const visit = (node, depth = 0) => {
    const children = Array.isArray(node?.children) ? node.children : [];
    const nodeId = normalizedId(node?.occurrenceId || node?.id);
    if (!children.length) {
      const part = partById.get(nodeId);
      return part ? [part.id] : [];
    }
    const occurrenceIds = [...new Set(children.flatMap((child) => visit(child, depth + 1)))];
    if (occurrenceIds.length > 1) {
      targets.push({
        id: `group:${nodeId || targets.length}`,
        label: String(node?.displayName || node?.label || node?.name || "Group").trim() || "Group",
        occurrenceIds,
        depth: Math.max(depth - 1, 0),
        group: true
      });
    }
    return occurrenceIds;
  };
  if (meshData?.assemblyRoot) visit(meshData.assemblyRoot);
  parts.forEach((part, index) => {
    targets.push({
      ...part,
      label: displayPartLabel(part, index, parts.length, scope),
      occurrenceIds: [part.id],
      depth: 0,
      group: false
    });
  });
  return targets;
}

export function sourceMaterialFallbackColor(effectiveAppearance, materialId, parts, neutral = "#b8b8b8") {
  const id = normalizedId(materialId);
  const assigned = (Array.isArray(parts) ? parts : []).filter((part) => (
    normalizedId(effectiveAppearance?.assignments?.[normalizedId(part?.id)]) === id
  ));
  if (!assigned.length) return neutral;
  const colors = assigned.map((part) => {
    const color = String(part?.color || "").trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(color) ? color : "";
  });
  if (colors.some((color) => !color)) return neutral;
  return colors.every((color) => color === colors[0]) ? colors[0] : neutral;
}

export function patchSourceMaterialOverlay(overlay, materialId, patch) {
  const current = sessionOverlay(overlay);
  const id = normalizedId(materialId);
  if (!id) return current;
  return {
    materials: {
      ...current.materials,
      [id]: { ...(current.materials[id] || {}), ...(patch || {}) }
    },
    assignments: { ...current.assignments }
  };
}

function assignSourceMaterialOverlay(overlay, occurrenceIds, materialId) {
  const current = sessionOverlay(overlay);
  const id = normalizedId(materialId);
  const assignments = { ...current.assignments };
  for (const occurrenceId of Array.isArray(occurrenceIds) ? occurrenceIds : []) {
    const normalizedOccurrenceId = normalizedId(occurrenceId);
    if (normalizedOccurrenceId && id) assignments[normalizedOccurrenceId] = id;
  }
  return { materials: { ...current.materials }, assignments };
}

function nextSourceMaterialCopyId(appearance, overlay, sourceId) {
  const prefix = `${normalizedId(sourceId) || "material"}-copy`;
  const effective = effectiveSourceAppearance(appearance, overlay);
  const ids = new Set(Object.keys(effective?.materials || {}));
  let index = 1;
  while (ids.has(`${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

export function duplicateSourceMaterialOverlay(appearance, overlay, sourceId, occurrenceIds) {
  const effective = effectiveSourceAppearance(appearance, overlay);
  const source = effective?.materials?.[normalizedId(sourceId)];
  if (!source) return sessionOverlay(overlay);
  const materialId = nextSourceMaterialCopyId(appearance, overlay, sourceId);
  const name = `${String(source.name || "Material").trim() || "Material"} copy`;
  const next = patchSourceMaterialOverlay(overlay, materialId, { ...source, name });
  return {
    overlay: assignSourceMaterialOverlay(next, occurrenceIds, materialId),
    materialId
  };
}

export function sourceMaterialEditorValue(material, key, fallbackColor = "#b8b8b8") {
  if (key === "baseColor") {
    return String(material?.baseColor || fallbackColor || "#b8b8b8").toLowerCase();
  }
  const value = Number(material?.[key]);
  if (Number.isFinite(value)) return Math.min(Math.max(value, 0), 1);
  return SOURCE_MATERIAL_DEFAULTS[key];
}

export function applySourceMaterialOverlayToMeshData(meshData, overlay, appearance = meshData?.appearance) {
  if (!meshData) return meshData;
  const effective = effectiveSourceAppearance(appearance, overlay);
  if (!effective) return meshData;
  const parts = (Array.isArray(meshData.parts) ? meshData.parts : []).map((part) => {
    const occurrenceId = normalizedId(part?.occurrenceId || part?.id);
    const materialId = normalizedId(effective.assignments?.[occurrenceId]);
    const material = effective.materials?.[materialId];
    if (!material) return part;
    const channels = {
      roughness: sourceMaterialEditorValue(material, "roughness"),
      metalness: sourceMaterialEditorValue(material, "metalness"),
      clearcoat: sourceMaterialEditorValue(material, "clearcoat"),
      clearcoatRoughness: sourceMaterialEditorValue(material, "clearcoatRoughness"),
      opacity: sourceMaterialEditorValue(material, "opacity")
    };
    const sourceOpacity = Number.isFinite(Number(part?.sourceOpacity))
      ? Math.min(Math.max(Number(part.sourceOpacity), 0), 1)
      : 1;
    return {
      ...part,
      materialId,
      materialName: material.name,
      color: material.baseColor || part.sourceColor || null,
      material: channels,
      opacity: sourceOpacity * channels.opacity
    };
  });
  const displayed = { ...meshData, appearance: effective, parts };
  materialGeometrySources.set(displayed, sourceMaterialGeometry(meshData));
  return displayed;
}
