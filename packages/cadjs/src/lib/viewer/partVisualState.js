import { syncLineMaterialOpacity } from "../../common/renderEdges.js";
import {
  CAD_DISPLAY_MODE,
  displayModeUsesTransparentSurfaces
} from "../../common/displaySettings.js";
import { REFERENCE_SELECTED_COLOR } from "./referenceGeometry.js";
import { BASE_VIEWER_THEME } from "./stageTheme.js";
import { readSourceColor } from "./surfaceMaterials.js";

const CAD_EDGE_OPACITY = 0.84;
const PART_HIGHLIGHT_SURFACE_RENDER_ORDER = 23;
const PART_HIGHLIGHT_EDGE_RENDER_ORDER = 26;
const PART_HOVER_OPACITY_BOOST = 0.08;
const PART_SELECTED_OPACITY_BOOST = 0.12;
export const FOCUSED_DIMMED_SURFACE_OPACITY = 0.035;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function getPartHighlightColors(THREE, {
  edgeSettings = null
} = {}) {
  const highlightColor = String(edgeSettings?.highlightColor || REFERENCE_SELECTED_COLOR).trim() || REFERENCE_SELECTED_COLOR;
  return {
    hoveredSurfaceColor: new THREE.Color(highlightColor),
    hoveredEdgeColor: new THREE.Color(highlightColor),
    selectedSurfaceColor: new THREE.Color(highlightColor),
    selectedEdgeColor: new THREE.Color(highlightColor)
  };
}

export function normalizePartIdList(value) {
  return (Array.isArray(value) ? value : [value])
    .map((id) => String(id || "").trim())
    .filter(Boolean);
}

export function referenceMatchesFocusedPart(reference, focusedPartIdSet) {
  if (!focusedPartIdSet?.size) {
    return true;
  }
  const partId = String(reference?.partId || "").trim();
  return partId
    ? focusedPartIdSet.has(partId)
    : focusedPartIdSet.has("__model__");
}

function baseObjectRenderOrder(record, object, fieldName) {
  if (!object) {
    return 0;
  }
  if (!Number.isFinite(Number(record[fieldName]))) {
    record[fieldName] = Number.isFinite(Number(object.renderOrder)) ? Number(object.renderOrder) : 0;
  }
  return record[fieldName];
}

function syncHighlightRenderOrder(record, object, fieldName, highlighted, highlightRenderOrder) {
  if (!object) {
    return;
  }
  const baseRenderOrder = baseObjectRenderOrder(record, object, fieldName);
  object.renderOrder = highlighted ? highlightRenderOrder : baseRenderOrder;
}

function syncSurfaceTransparency(record, forceTransparent, opacity, {
  writeTransparentDepth = true
} = {}) {
  const material = record?.material;
  if (!material) {
    return;
  }
  if (!Object.hasOwn(record, "baseDepthWrite")) {
    record.baseDepthWrite = material.depthWrite !== false;
  }
  const nextTransparent = forceTransparent || opacity < 0.999;
  if (material.transparent !== nextTransparent) {
    material.transparent = nextTransparent;
    material.needsUpdate = true;
  }
  material.depthWrite = nextTransparent && !writeTransparentDepth ? false : record.baseDepthWrite;
}

const CAD_SURFACE_EDGE_OPACITY_UNIFORMS = Object.freeze({
  feature: "cadSurfaceFeatureOpacity",
  tangent: "cadSurfaceTangentOpacity",
  seam: "cadSurfaceSeamOpacity",
  degenerate: "cadSurfaceDegenerateOpacity"
});

function syncCadSurfaceEdgeHighlight(THREE, record, edgeColor, edgeOpacity = null) {
  const material = record?.material;
  const userData = material?.userData;
  if (!material || userData?.cadSurfaceEdges !== true) {
    return;
  }
  const nextColor = edgeColor?.isColor
    ? edgeColor
    : readSourceColor(THREE, edgeColor) || userData.cadSurfaceEdgeBaseColor;
  if (nextColor?.isColor) {
    userData.cadSurfaceEdgeColor = nextColor.clone();
    const colorUniform = userData.cadSurfaceEdgeShader?.uniforms?.cadSurfaceEdgeColor;
    if (colorUniform?.value?.copy) {
      colorUniform.value.copy(nextColor);
    }
  }

  const highlightedOpacity = edgeOpacity !== null && edgeOpacity !== undefined && Number.isFinite(Number(edgeOpacity))
    ? clamp(Number(edgeOpacity), 0, 1)
    : null;
  const baseClassSettings = userData.cadSurfaceEdgeBaseClassSettings || {};
  const uniforms = userData.cadSurfaceEdgeShader?.uniforms || null;
  for (const [classId, uniformName] of Object.entries(CAD_SURFACE_EDGE_OPACITY_UNIFORMS)) {
    const baseOpacity = Number(baseClassSettings[classId]?.opacity);
    const nextOpacity = highlightedOpacity === null
      ? (Number.isFinite(baseOpacity) ? baseOpacity : null)
      : highlightedOpacity;
    if (nextOpacity === null) {
      continue;
    }
    userData[`cadSurfaceEdge${classId}Opacity`] = nextOpacity;
    if (uniforms?.[uniformName]) {
      uniforms[uniformName].value = nextOpacity;
    }
  }
}

export function applyPartVisualState(THREE, records, {
  viewerTheme,
  edgeSettings,
  hiddenPartIds,
  hoveredPartId,
  focusedPartId,
  selectedPartIds,
  showEdges,
  displayMode = CAD_DISPLAY_MODE.SOLID
}) {
  const hidden = new Set(Array.isArray(hiddenPartIds) ? hiddenPartIds : []);
  const selected = new Set(Array.isArray(selectedPartIds) ? selectedPartIds : []);
  const hovered = new Set(
    (Array.isArray(hoveredPartId) ? hoveredPartId : [hoveredPartId])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const baseEdgeColor = edgeSettings?.color || viewerTheme?.edge || BASE_VIEWER_THEME.edge;
  const defaultSurfaceOpacity = Number.isFinite(Number(viewerTheme?.surfaceOpacity))
    ? Number(viewerTheme.surfaceOpacity)
    : 1;
  const focusIds = new Set(normalizePartIdList(focusedPartId));
  const hasFocus = focusIds.size > 0;
  const baseEdgeOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (viewerTheme?.edgeOpacity ?? BASE_VIEWER_THEME.edgeOpacity ?? CAD_EDGE_OPACITY);
  const transparentDisplayMode = displayModeUsesTransparentSurfaces(displayMode);
  const highlightEdgeOpacity = Number.isFinite(Number(edgeSettings?.highlightOpacity))
    ? clamp(Number(edgeSettings.highlightOpacity), 0, 1)
    : 1;
  const {
    hoveredSurfaceColor,
    hoveredEdgeColor,
    selectedSurfaceColor,
    selectedEdgeColor
  } = getPartHighlightColors(THREE, { edgeSettings });

  for (const record of Array.isArray(records) ? records : []) {
    const effectStyle = record.effectStyle && typeof record.effectStyle === "object" ? record.effectStyle : {};
    const effectHidden = record.effectVisible === false;
    const effectColor = readSourceColor(THREE, effectStyle.color);
    const effectEdgeColor = readSourceColor(THREE, effectStyle.edgeColor);
    const effectEmissive = readSourceColor(THREE, effectStyle.emissive);
    const isHidden = hidden.has(record.partId);
    const isSelected = !isHidden && (selected.has(record.partId) || record.effectHighlighted === true);
    const isHovered = !isHidden && !effectHidden && hovered.has(record.partId);
    const isFocused = !isHidden && !effectHidden && hasFocus && focusIds.has(record.partId);
    const isDimmed = !isHidden && !effectHidden && hasFocus && !isFocused;
    const isHighlighted = isSelected || isHovered;

    record.mesh.visible = !effectHidden && !isHidden;
    if (record.edges) {
      record.edges.visible = showEdges && !effectHidden && !isHidden;
    }
    syncHighlightRenderOrder(record, record.mesh, "baseMeshRenderOrder", isHighlighted, PART_HIGHLIGHT_SURFACE_RENDER_ORDER);
    syncHighlightRenderOrder(record, record.edges, "baseEdgeRenderOrder", isHighlighted, PART_HIGHLIGHT_EDGE_RENDER_ORDER);

    const baseSurfaceOpacity = Number.isFinite(Number(record.baseOpacity))
      ? Number(record.baseOpacity)
      : defaultSurfaceOpacity;
    const effectOpacity = Number.isFinite(Number(effectStyle.opacity))
      ? clamp(Number(effectStyle.opacity), 0, 1)
      : 1;
    const effectEdgeOpacity = Number.isFinite(Number(effectStyle.edgeOpacity))
      ? clamp(Number(effectStyle.edgeOpacity), 0, 1)
      : effectOpacity;
    const highlightedEdgeOpacity = (isSelected || isHovered) ? highlightEdgeOpacity * effectEdgeOpacity : null;
    const dimmedSurfaceOpacity = Math.min(baseSurfaceOpacity * effectOpacity, FOCUSED_DIMMED_SURFACE_OPACITY);
    const baseEffectSurfaceOpacity = baseSurfaceOpacity * effectOpacity;
    const highlightedSurfaceOpacity = isHighlighted
      ? transparentDisplayMode
        ? clamp(
            baseEffectSurfaceOpacity + (isSelected ? PART_SELECTED_OPACITY_BOOST : PART_HOVER_OPACITY_BOOST) * effectOpacity,
            0,
            1
          )
        : clamp(highlightEdgeOpacity * effectOpacity, 0, 1)
      : baseEffectSurfaceOpacity;
    const nextSurfaceOpacity = isHidden ? 0 : isDimmed ? dimmedSurfaceOpacity : highlightedSurfaceOpacity;
    syncSurfaceTransparency(record, isHidden || isDimmed || isHighlighted, nextSurfaceOpacity, {
      writeTransparentDepth: !isHidden && !isDimmed && !transparentDisplayMode
    });
    record.material.opacity = nextSurfaceOpacity;

    if (record.baseColor && record.material.color) {
      record.material.color.copy(
        isSelected
          ? selectedSurfaceColor
          : isHovered
            ? hoveredSurfaceColor
            : effectColor || record.baseColor
      );
    }

    if ("emissive" in record.material && record.material.emissive) {
      if (isSelected) {
        record.material.emissive.copy(selectedSurfaceColor);
      } else if (isHovered) {
        record.material.emissive.copy(hoveredSurfaceColor);
      } else if (record.baseEmissiveColor && record.baseEmissiveIntensity > 0) {
        record.material.emissive.copy(record.baseEmissiveColor);
      } else {
        record.material.emissive.set(0x000000);
      }
      record.material.emissiveIntensity = isSelected
        ? 0.08
        : isHovered
          ? 0.12
          : effectEmissive
            ? clamp(Number(effectStyle.emissiveIntensity) || 0.22, 0, 2)
            : clamp(Number(record.baseEmissiveIntensity) || 0, 0, 2);
      if (!isSelected && !isHovered && effectEmissive) {
        record.material.emissive.copy(effectEmissive);
      }
    }

    const nextEdgeColor = isSelected
      ? selectedEdgeColor
      : isHovered
        ? hoveredEdgeColor
        : effectEdgeColor || baseEdgeColor;
    syncCadSurfaceEdgeHighlight(THREE, record, nextEdgeColor, highlightedEdgeOpacity);

    if (record.edgeMaterial) {
      record.edgeMaterial.color.set(nextEdgeColor);
      syncLineMaterialOpacity(record.edgeMaterial, isSelected
        ? highlightEdgeOpacity * effectEdgeOpacity
        : isHovered
          ? highlightEdgeOpacity * effectEdgeOpacity
          : isHidden || isDimmed
            ? nextSurfaceOpacity
            : baseEdgeOpacity * effectEdgeOpacity);
    }
  }
}
