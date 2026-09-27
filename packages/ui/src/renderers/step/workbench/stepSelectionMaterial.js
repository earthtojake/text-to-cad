const TOPOLOGY_SELECTOR = /^(.*)\.[sfe]\d+$/iu;
const SYNTHETIC_MODEL_IDS = new Set(["__step_model__", "__model__"]);
const MATERIAL_CHANNELS = Object.freeze([
  ["roughness", "Roughness"],
  ["metalness", "Metalness"],
  ["clearcoat", "Clearcoat"],
  ["clearcoatRoughness", "Coat roughness"],
  ["opacity", "Opacity"]
]);

function text(value) {
  return String(value || "").trim();
}

function normalizedColor(value) {
  const color = text(value).toUpperCase();
  return /^#[0-9A-F]{6}$/u.test(color) ? color : "";
}

function distinct(values) {
  return [...new Set(values.filter(Boolean))];
}

function selectorOccurrence(item) {
  const selector = text(item?.displaySelector || item?.normalizedSelector || item?.id);
  const match = selector.match(TOPOLOGY_SELECTOR);
  return match ? text(match[1]) : selector;
}

function leafIds(node) {
  const declared = Array.isArray(node?.leafPartIds) ? node.leafPartIds.map(text).filter(Boolean) : [];
  if (declared.length) return distinct(declared);
  const leaves = [];
  const stack = node ? [node] : [];
  while (stack.length) {
    const current = stack.pop();
    const children = Array.isArray(current?.children) ? current.children : [];
    if (children.length) {
      for (let index = children.length - 1; index >= 0; index -= 1) stack.push(children[index]);
      continue;
    }
    leaves.push(text(current?.occurrenceId), text(current?.id));
  }
  return distinct(leaves);
}

function targetIds(item) {
  if (!item) return [];
  if (item.pickData || ["face", "edge", "shape", "occurrence"].includes(text(item.selectorType))) {
    return distinct([
      text(item.occurrenceId),
      text(item.pickData?.occurrenceId),
      selectorOccurrence(item)
    ]);
  }
  return distinct([...leafIds(item), text(item.occurrenceId), text(item.id)]);
}

function partId(part) {
  return text(part?.occurrenceId || part?.id);
}

function addToIndex(index, key, value) {
  const normalized = text(key);
  if (!normalized) return;
  const rows = index.get(normalized) || [];
  if (!rows.includes(value)) rows.push(value);
  index.set(normalized, rows);
}

function partIndex(parts) {
  const index = new Map();
  for (const part of parts) {
    addToIndex(index, part?.occurrenceId, part);
    addToIndex(index, part?.id, part);
  }
  return index;
}

function assemblyNodeIndex(root) {
  const index = new Map();
  const stack = root ? [root] : [];
  while (stack.length) {
    const node = stack.pop();
    const ids = distinct([text(node?.occurrenceId), text(node?.id)]);
    for (const id of ids) if (!index.has(id)) index.set(id, node);
    const children = Array.isArray(node?.children) ? node.children : [];
    for (let childIndex = children.length - 1; childIndex >= 0; childIndex -= 1) stack.push(children[childIndex]);
  }
  return index;
}

function allEqual(values) {
  return values.length > 0 && values.every((value) => Object.is(value, values[0]));
}

function commonNumber(rows, read) {
  const values = rows.map(read).map(Number).filter(Number.isFinite);
  return values.length === rows.length && allEqual(values) ? values[0] : null;
}

function renderMaterial(parts) {
  const materialIds = parts.map((part) => text(part?.materialId));
  const materialNames = parts.map((part) => text(part?.materialName));
  const materialId = materialIds.length && allEqual(materialIds) ? materialIds[0] : "";
  const name = materialNames.length && allEqual(materialNames) ? materialNames[0] : "";
  if (!materialId && !name) return null;
  const materialRows = parts.map((part) => (
    part?.material && typeof part.material === "object" && !Array.isArray(part.material)
      ? part.material
      : {}
  ));
  const material = {};
  for (const [key] of MATERIAL_CHANNELS) {
    const value = commonNumber(materialRows, (row) => row[key]);
    if (value !== null) material[key] = value;
  }
  return { materialId, name, material };
}

function colorForParts(material, parts) {
  const authored = normalizedColor(material?.baseColor);
  if (authored) return { value: authored, mixed: false };
  const colors = parts.map((part) => normalizedColor(
    part?.sourceColor || part?.baseColor || part?.color
  ));
  if (!colors.length || colors.every((color) => !color)) return null;
  if (colors.some((color) => !color) || !allEqual(colors)) return { value: "", mixed: true };
  return { value: colors[0], mixed: false };
}

function channelsFor(material, fallbackMaterial = null) {
  const source = material && typeof material === "object" ? material : fallbackMaterial;
  if (!source || typeof source !== "object") return [];
  return MATERIAL_CHANNELS.flatMap(([key, label]) => {
    if (!Object.hasOwn(source, key)) return [];
    const value = Number(source[key]);
    return Number.isFinite(value) ? [{ key, label, value }] : [];
  });
}

function materialFact(occurrenceId, parts, appearance) {
  const assignedId = text(appearance?.assignments?.[occurrenceId]);
  const authored = assignedId && appearance?.materials?.[assignedId] && typeof appearance.materials[assignedId] === "object"
    ? appearance.materials[assignedId]
    : null;
  // A supplied appearance block is authoritative. If it deliberately leaves an
  // occurrence unassigned, an older mesh publication must not revive its stale
  // materialId/materialName while the replacement display wrapper is settling.
  const rendered = assignedId || !appearance ? renderMaterial(parts) : null;
  const materialId = assignedId || rendered?.materialId || "";
  const name = text(authored?.name || rendered?.name);
  const assigned = Boolean(materialId || name);
  const identity = assigned
    ? (materialId ? `id:${materialId}` : `name:${name}:${JSON.stringify(rendered?.material || {})}`)
    : "unassigned";
  return {
    assigned,
    identity,
    materialId,
    name: name || (assigned ? materialId : "Unassigned"),
    color: colorForParts(authored, parts),
    channels: channelsFor(authored, rendered?.material)
  };
}

function targetOccurrences(items, meshData, appearance) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts.filter(Boolean) : [];
  const partsById = partIndex(parts);
  const assemblyById = assemblyNodeIndex(meshData?.assemblyRoot);
  const targets = [];
  for (const item of items) {
    const directIds = targetIds(item);
    const ids = distinct(directIds.flatMap((id) => {
      const assemblyNode = assemblyById.get(id);
      return assemblyNode ? leafIds(assemblyNode) : [id];
    }));
    if (ids.some((id) => SYNTHETIC_MODEL_IDS.has(id))) {
      for (const part of parts) targets.push({ occurrenceId: partId(part), parts: [part] });
      continue;
    }
    let resolved = false;
    for (const id of ids) {
      const matched = partsById.get(id) || [];
      if (matched.length) {
        targets.push({ occurrenceId: partId(matched[0]) || id, parts: matched });
        resolved = true;
      } else if (Object.hasOwn(appearance?.assignments || {}, id)) {
        targets.push({ occurrenceId: id, parts: [] });
        resolved = true;
      }
    }
    if (!resolved && ids[0]) targets.push({ occurrenceId: ids[0], parts: [] });
  }
  const byOccurrence = new Map();
  for (const target of targets) {
    const id = text(target.occurrenceId);
    if (!id) continue;
    const current = byOccurrence.get(id) || [];
    byOccurrence.set(id, [...current, ...target.parts.filter((part) => !current.includes(part))]);
  }
  return [...byOccurrence.entries()].map(([occurrenceId, occurrenceParts]) => ({ occurrenceId, parts: occurrenceParts }));
}

function commonColor(facts) {
  const colors = facts.map((fact) => fact.color);
  if (colors.every((color) => !color)) return null;
  if (colors.some((color) => !color || color.mixed)) return { value: "", mixed: true };
  const values = colors.map((color) => color.value);
  return allEqual(values) ? colors[0] : { value: "", mixed: true };
}

function commonChannels(facts) {
  if (!facts.length) return [];
  const first = facts[0].channels;
  return first.filter((channel) => facts.every((fact) => fact.channels.some((candidate) => (
    candidate.key === channel.key && Object.is(candidate.value, channel.value)
  ))));
}

/**
 * Summarize only declared material metadata for the current STEP selection.
 * Source colors remain colors; they never imply a named or physical material.
 */
export function stepSelectionMaterialInfo({ references = [], meshData = null, appearance = null } = {}) {
  const items = Array.isArray(references) ? references.filter(Boolean) : [];
  if (!items.length) return null;
  const targets = targetOccurrences(items, meshData, appearance);
  if (!targets.length) return null;
  const facts = targets.map(({ occurrenceId, parts }) => materialFact(occurrenceId, parts, appearance));
  const identities = distinct(facts.map((fact) => fact.identity));
  if (identities.length > 1) {
    return { status: "mixed", label: "Mixed", color: null, channels: [] };
  }
  const assigned = facts[0]?.assigned === true;
  return {
    status: assigned ? "assigned" : "unassigned",
    label: assigned ? facts[0].name : "Unassigned",
    color: commonColor(facts),
    channels: assigned ? commonChannels(facts) : []
  };
}
