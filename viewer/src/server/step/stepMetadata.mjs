import fs from "node:fs";

export const TEXT_TO_CAD_GENERATOR = "cadpy";
export const TEXT_TO_CAD_GENERATOR_PROPERTY = "cadpy:generator";
export const TEXT_TO_CAD_ENTRY_KIND_PROPERTY = "cadpy:entryKind";
export const TEXT_TO_CAD_SOURCE_PATH_PROPERTY = "cadpy:sourcePath";
export const TEXT_TO_CAD_SOURCE_HASH_PROPERTY = "cadpy:sourceHash";

const STEP_STRING_PATTERN = "'(?:''|[^'])*'";

function unescapeStepString(value) {
  const raw = String(value || "").trim();
  const unquoted = raw.startsWith("'") && raw.endsWith("'") ? raw.slice(1, -1) : raw;
  return unquoted.replace(/''/g, "'");
}

export function normalizeTextToCadEntryKind(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "part" || normalized === "assembly" ? normalized : "";
}

export function readTextToCadStepMetadataText(stepText) {
  const text = String(stepText || "");
  const descriptiveItems = new Map();
  const descriptivePattern = new RegExp(
    `#(\\d+)\\s*=\\s*DESCRIPTIVE_REPRESENTATION_ITEM\\s*\\(\\s*(${STEP_STRING_PATTERN})\\s*,\\s*(${STEP_STRING_PATTERN})\\s*\\)\\s*;`,
    "gis",
  );
  for (const match of text.matchAll(descriptivePattern)) {
    descriptiveItems.set(`#${match[1]}`, {
      value: unescapeStepString(match[3]),
    });
  }

  const representations = new Map();
  const representationPattern = new RegExp(
    `#(\\d+)\\s*=\\s*REPRESENTATION\\s*\\(\\s*(${STEP_STRING_PATTERN})\\s*,\\s*\\(([^)]*)\\)\\s*,\\s*#\\d+\\s*\\)\\s*;`,
    "gis",
  );
  for (const match of text.matchAll(representationPattern)) {
    representations.set(`#${match[1]}`, {
      itemRefs: Array.from(String(match[3] || "").matchAll(/#\d+/g), (itemMatch) => itemMatch[0]),
    });
  }

  const propertyDefinitions = new Map();
  const propertyPattern = new RegExp(
    `#(\\d+)\\s*=\\s*PROPERTY_DEFINITION\\s*\\(\\s*(${STEP_STRING_PATTERN})\\s*,\\s*(${STEP_STRING_PATTERN})\\s*,\\s*#[0-9]+\\s*\\)\\s*;`,
    "gis",
  );
  for (const match of text.matchAll(propertyPattern)) {
    const propertyName = unescapeStepString(match[3]);
    if (
      propertyName === TEXT_TO_CAD_GENERATOR_PROPERTY ||
      propertyName === TEXT_TO_CAD_ENTRY_KIND_PROPERTY ||
      propertyName === TEXT_TO_CAD_SOURCE_PATH_PROPERTY ||
      propertyName === TEXT_TO_CAD_SOURCE_HASH_PROPERTY ||
      propertyName === "cadpy:entry_kind"
    ) {
      propertyDefinitions.set(`#${match[1]}`, propertyName);
    }
  }

  const metadata = {};
  const linkPattern = /#\d+\s*=\s*PROPERTY_DEFINITION_REPRESENTATION\s*\(\s*(#\d+)\s*,\s*(#\d+)\s*\)\s*;/gis;
  for (const match of text.matchAll(linkPattern)) {
    const propertyName = propertyDefinitions.get(match[1]);
    const representation = representations.get(match[2]);
    if (!propertyName || !representation) {
      continue;
    }
    const item = representation.itemRefs.map((itemRef) => descriptiveItems.get(itemRef)).find(Boolean);
    if (!item) {
      continue;
    }
    if (propertyName === TEXT_TO_CAD_GENERATOR_PROPERTY) {
      metadata.generator = item.value;
    } else if (
      propertyName === TEXT_TO_CAD_ENTRY_KIND_PROPERTY ||
      propertyName === "cadpy:entry_kind"
    ) {
      const entryKind = normalizeTextToCadEntryKind(item.value);
      if (entryKind) {
        metadata.entryKind = entryKind;
      }
    } else if (propertyName === TEXT_TO_CAD_SOURCE_HASH_PROPERTY) {
      metadata.sourceHash = item.value;
    } else if (propertyName === TEXT_TO_CAD_SOURCE_PATH_PROPERTY) {
      metadata.sourcePath = item.value;
    }
  }
  return metadata;
}

export function readTextToCadStepMetadataFile(stepPath) {
  return readTextToCadStepMetadataText(fs.readFileSync(stepPath, "utf-8"));
}
