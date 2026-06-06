import {
  buildTopologyDisplayEdgePolylines,
  buildTopologyDisplayEdgePositions
} from "./topologyDisplayEdges.js";
import {
  displayModeIsWireframe
} from "./displaySettings.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

const DEFAULT_LINE_DEPTH_BIAS = 0;
// Keep topology edges slightly above coplanar faces without letting nearby solids lose the depth test.
export const TOPOLOGY_LINE_DEPTH_BIAS = 0.0045;
const TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL = 0.00025;
const MAX_TOPOLOGY_LINE_DEPTH_BIAS = 0.006;
const COPLANAR_TOPOLOGY_EDGE_CLASSES = new Set(["tangent", "seam"]);
const COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS = 0.006;
const COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL = 0.00025;
const MAX_COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS = 0.008;
const DEFAULT_VISIBLE_TOPOLOGY_EDGE_CLASSES = Object.freeze(["feature"]);
const TOPOLOGY_EDGE_CLASS_ORDER = Object.freeze(["feature", "tangent", "seam", "degenerate"]);
const MAX_TOPOLOGY_LINE_STRIP_POLYLINES = 1200;
const MAX_TOPOLOGY_LINE_STRIP_POSITION_VALUES = 180000;
const DEFAULT_TOPOLOGY_EDGE_CLASS_SETTINGS = Object.freeze({
  feature: Object.freeze({ opacity: 1, thickness: 1.15 }),
  tangent: Object.freeze({ opacity: 0.5, thickness: 1.15 }),
  seam: Object.freeze({ opacity: 0.85, thickness: 1.15 }),
  degenerate: Object.freeze({ opacity: 1, thickness: 0 })
});

export function topologyLineDepthBiasForWidth(lineWidth = 1, { visibilityClass = "" } = {}) {
  const width = Number.isFinite(Number(lineWidth))
    ? Math.max(1, Number(lineWidth))
    : 1;
  const normalizedClass = String(visibilityClass || "").trim().toLowerCase();
  const baseBias = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS
    : TOPOLOGY_LINE_DEPTH_BIAS;
  const biasPerExtraPixel = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL
    : TOPOLOGY_LINE_DEPTH_BIAS_PER_EXTRA_PIXEL;
  const maxBias = COPLANAR_TOPOLOGY_EDGE_CLASSES.has(normalizedClass)
    ? MAX_COPLANAR_TOPOLOGY_LINE_DEPTH_BIAS
    : MAX_TOPOLOGY_LINE_DEPTH_BIAS;
  return clamp(
    baseBias + Math.max(0, width - 1) * biasPerExtraPixel,
    baseBias,
    maxBias
  );
}

export function lineSegmentPositionsFromGeometry(geometry) {
  const positionAttribute = geometry?.getAttribute?.("position");
  const rawPositions = positionAttribute?.array;
  if (!positionAttribute?.count || !rawPositions?.length) {
    return null;
  }
  return rawPositions;
}

export function syncLineMaterialOpacity(material, opacity) {
  if (!material) {
    return;
  }
  const nextOpacity = clamp(Number(opacity) || 0, 0, 1);
  const nextTransparent = nextOpacity < 0.999;
  material.opacity = nextOpacity;
  material.depthWrite = false;
  if (material.transparent !== nextTransparent) {
    material.transparent = nextTransparent;
    material.needsUpdate = true;
  }
}

export function syncScreenSpaceLineMaterialResolution(materials, width, height) {
  const nextWidth = Math.max(1, Math.floor(Number(width) || 1));
  const nextHeight = Math.max(1, Math.floor(Number(height) || 1));
  for (const material of materials || []) {
    material?.resolution?.set?.(nextWidth, nextHeight);
  }
}

function registerLineMaterial(context = {}, material, materials = null) {
  materials?.add?.(material);
  context.registerScreenSpaceLineMaterial?.(material);
}

function unregisterLineMaterial(context = {}, material, materials = null) {
  materials?.delete?.(material);
  context.unregisterScreenSpaceLineMaterial?.(material);
}

function normalizePartIds(value) {
  return (Array.isArray(value) ? value : [value])
    .map((id) => String(id || "").trim())
    .filter(Boolean);
}

function occurrenceMatchesPartIds(occurrenceId, partIds = []) {
  const normalizedOccurrenceId = String(occurrenceId || "").trim();
  if (!normalizedOccurrenceId || !partIds.length) {
    return false;
  }
  return partIds.some((partId) => (
    normalizedOccurrenceId === partId ||
    normalizedOccurrenceId.startsWith(`${partId}.`)
  ));
}

function topologyEdgeRowMatchesPartIds(row, partIds = []) {
  return occurrenceMatchesPartIds(row?.occurrenceId || row?.partId || row?.id, partIds);
}

function topologyEdgeRowMatchesLineStripFilters(row, {
  includePartIds = [],
  excludePartIds = [],
  visibilityClasses = []
} = {}) {
  if (includePartIds.length && !topologyEdgeRowMatchesPartIds(row, includePartIds)) {
    return false;
  }
  if (excludePartIds.length && topologyEdgeRowMatchesPartIds(row, excludePartIds)) {
    return false;
  }
  if (visibilityClasses.length) {
    const visibilityClass = String(row?.visibilityClass || "feature").trim().toLowerCase() || "feature";
    if (!visibilityClasses.includes(visibilityClass)) {
      return false;
    }
  }
  return true;
}

function shouldBuildTopologyLineStrips(selectorRuntime, filters = {}) {
  const edgeRows = Array.isArray(selectorRuntime?.edges) ? selectorRuntime.edges : [];
  if (!edgeRows.length) {
    return false;
  }
  let polylineCount = 0;
  let positionValueCount = 0;
  for (const row of edgeRows) {
    if (!topologyEdgeRowMatchesLineStripFilters(row, filters)) {
      continue;
    }
    const segmentCount = Number.isFinite(Number(row?.segmentCount))
      ? Math.max(1, Number(row.segmentCount))
      : 1;
    polylineCount += 1;
    positionValueCount += (segmentCount + 1) * 3;
    if (
      polylineCount > MAX_TOPOLOGY_LINE_STRIP_POLYLINES ||
      positionValueCount > MAX_TOPOLOGY_LINE_STRIP_POSITION_VALUES
    ) {
      return false;
    }
  }
  return polylineCount > 0;
}

function normalizeVisibilityClasses(value, fallback = DEFAULT_VISIBLE_TOPOLOGY_EDGE_CLASSES) {
  const values = (Array.isArray(value) ? value : [value])
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean);
  return values.length ? values : fallback;
}

function normalizeTopologyEdgeClassSettings(edgeSettings = {}, baseTheme = {}, fallbackClasses = DEFAULT_VISIBLE_TOPOLOGY_EDGE_CLASSES) {
  const classSettings = edgeSettings?.classes && typeof edgeSettings.classes === "object"
    ? edgeSettings.classes
    : null;
  const explicitVisibilityClasses = classSettings
    ? []
    : normalizeVisibilityClasses(edgeSettings?.visibilityClasses, fallbackClasses);
  const baseOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (baseTheme?.edgeOpacity ?? 0.84);
  const baseThickness = Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : (baseTheme?.edgeThickness ?? 1);

  if (!classSettings) {
    return explicitVisibilityClasses.map((classId) => ({
      classId,
      opacity: baseOpacity,
      thickness: baseThickness
    }));
  }

  return TOPOLOGY_EDGE_CLASS_ORDER
    .map((classId) => {
      const classValue = classSettings[classId] || DEFAULT_TOPOLOGY_EDGE_CLASS_SETTINGS[classId];
      const classOpacity = Number.isFinite(Number(classValue.opacity))
        ? clamp(Number(classValue.opacity), 0, 1)
        : DEFAULT_TOPOLOGY_EDGE_CLASS_SETTINGS[classId].opacity;
      const classThickness = Number.isFinite(Number(classValue.thickness))
        ? clamp(Number(classValue.thickness), 0, 6)
        : DEFAULT_TOPOLOGY_EDGE_CLASS_SETTINGS[classId].thickness;
      if (classThickness <= 0 || classOpacity <= 0) {
        return null;
      }
      return {
        classId,
        opacity: classOpacity,
        thickness: classThickness
      };
    })
    .filter(Boolean);
}

function runtimeHasVisibilityClassRows(selectorRuntime) {
  return Array.isArray(selectorRuntime?.edges) &&
    selectorRuntime.edges.some((row) => String(row?.visibilityClass || "").trim());
}

export function createScreenSpaceLineSegments(context = {}, positions, {
  color,
  opacity = 1,
  lineWidth = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}, materials = null) {
  const LineSegments2 = context.LineSegments2;
  const LineSegmentsGeometry = context.LineSegmentsGeometry;
  const LineMaterial = context.LineMaterial;
  if (
    !LineSegments2 ||
    !LineSegmentsGeometry ||
    !LineMaterial ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    !positions.length
  ) {
    return null;
  }

  const lineGeometry = new LineSegmentsGeometry();
  lineGeometry.setPositions(positions);
  const lineMaterial = createScreenSpaceLineMaterial(LineMaterial, {
    color,
    opacity,
    lineWidth,
    depthTest,
    depthWrite,
    depthBias
  });
  registerLineMaterial(context, lineMaterial, materials);
  const line = new LineSegments2(lineGeometry, lineMaterial);
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.beforeDispose = () => {
    unregisterLineMaterial(context, lineMaterial, materials);
  };
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

function createScreenSpaceLineMaterial(LineMaterial, {
  color,
  opacity = 1,
  lineWidth = 1,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}) {
  const lineMaterial = new LineMaterial({
    color,
    linewidth: lineWidth,
    opacity,
    depthTest,
    depthWrite,
    toneMapped: false,
    worldUnits: false
  });
  syncLineMaterialOpacity(lineMaterial, opacity);
  applyLineDepthBias(lineMaterial, depthBias);
  return lineMaterial;
}

export function applyLineDepthBias(material, depthBias = DEFAULT_LINE_DEPTH_BIAS) {
  const bias = clamp(Number(depthBias) || 0, 0, 0.01);
  if (!material || bias <= 0) {
    return material;
  }
  material.polygonOffset = true;
  material.polygonOffsetFactor = 0;
  material.polygonOffsetUnits = -clamp(Math.round(bias * 1000), 1, 10);
  material.needsUpdate = true;
  return material;
}

export function createScreenSpaceLineStrip(context = {}, positions, {
  color,
  opacity = 1,
  lineWidth = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}, materials = null) {
  const Line2 = context.Line2;
  const LineGeometry = context.LineGeometry;
  const LineMaterial = context.LineMaterial;
  if (
    !Line2 ||
    !LineGeometry ||
    !LineMaterial ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    positions.length < 6
  ) {
    return null;
  }

  const lineGeometry = new LineGeometry();
  lineGeometry.setPositions(positions);
  const lineMaterial = createScreenSpaceLineMaterial(LineMaterial, {
    color,
    opacity,
    lineWidth,
    depthTest,
    depthWrite,
    depthBias
  });
  registerLineMaterial(context, lineMaterial, materials);
  const line = new Line2(lineGeometry, lineMaterial);
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.beforeDispose = () => {
    unregisterLineMaterial(context, lineMaterial, materials);
  };
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

export function createBasicLineStrip(context = {}, positions, {
  color,
  opacity = 1,
  lineWidth = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}) {
  const THREE = context.THREE;
  if (
    !THREE ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    positions.length < 6
  ) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  const positionArray = positions instanceof Float32Array ? positions : new Float32Array(positions);
  geometry.setAttribute("position", new THREE.BufferAttribute(positionArray, 3));
  const material = new THREE.LineBasicMaterial({
    color,
    linewidth: Number.isFinite(Number(lineWidth)) ? Number(lineWidth) : 1,
    transparent: Number(opacity) < 0.999,
    opacity: clamp(Number(opacity) || 0, 0, 1),
    depthTest,
    depthWrite,
    toneMapped: false
  });
  applyLineDepthBias(material, depthBias);
  const line = new THREE.Line(geometry, material);
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

export function createBasicLineSegments(context = {}, positions, {
  color,
  opacity = 1,
  renderOrder = 3,
  depthTest = true,
  depthWrite = false,
  depthBias = DEFAULT_LINE_DEPTH_BIAS
} = {}) {
  const THREE = context.THREE;
  if (
    !THREE ||
    !(Array.isArray(positions) || ArrayBuffer.isView(positions)) ||
    positions.length < 6
  ) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  const positionArray = positions instanceof Float32Array ? positions : new Float32Array(positions);
  geometry.setAttribute("position", new THREE.BufferAttribute(positionArray, 3));
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: Number(opacity) < 0.999,
    opacity: clamp(Number(opacity) || 0, 0, 1),
    depthTest,
    depthWrite,
    toneMapped: false
  });
  applyLineDepthBias(material, depthBias);
  const line = new THREE.LineSegments(geometry, material);
  line.renderOrder = renderOrder;
  line.frustumCulled = false;
  line.userData.disposeGeometry = true;
  line.userData.disposeMaterial = true;
  return line;
}

export function createScreenSpaceLineSegmentsFromGeometry(context, geometry, options, materials = null) {
  const positions = lineSegmentPositionsFromGeometry(geometry);
  return positions ? createScreenSpaceLineSegments(context, positions, options, materials) : null;
}

export function createDisplayEdgeObject(context = {}, {
  geometry,
  edgeSettings,
  baseTheme,
  partId,
  displayMode,
  thickness,
  wireframeEdgeColor = ""
}, materials = null) {
  const THREE = context.THREE;
  const wireframeMode = displayModeIsWireframe(displayMode);
  const depthTest = edgeSettings?.depthTest === false ? false : true;
  const edgeOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (baseTheme?.edgeOpacity ?? 0.84);
  const color = wireframeMode
    ? (wireframeEdgeColor || edgeSettings?.color || baseTheme?.edge || "#18181b")
    : (edgeSettings?.color || baseTheme?.edge || "#18181b");
  if (wireframeMode && THREE) {
    const opacity = Math.max(edgeOpacity, 0.9);
    const material = new THREE.LineBasicMaterial({
      color,
      transparent: opacity < 0.999,
      opacity,
      depthTest: false,
      depthWrite: false,
      toneMapped: false
    });
    const line = new THREE.LineSegments(geometry, material);
    line.renderOrder = 4;
    line.frustumCulled = false;
    line.userData.partId = partId;
    return { edgeMesh: line, edgeMaterial: material };
  }

  const line = createScreenSpaceLineSegmentsFromGeometry(context, geometry, {
    color,
    opacity: edgeOpacity,
    lineWidth: Number.isFinite(Number(thickness)) ? Number(thickness) : 1,
    renderOrder: 3,
    depthTest,
    depthWrite: false,
    depthBias: topologyLineDepthBiasForWidth(thickness)
  }, materials);
  if (!line) {
    return { edgeMesh: null, edgeMaterial: null };
  }
  line.userData.partId = partId;
  return { edgeMesh: line, edgeMaterial: line.material };
}

export function createTopologyDisplayEdgeObject(context = {}, selectorRuntime, edgeSettings, baseTheme, materials = null) {
  const includePartIds = normalizePartIds(edgeSettings?.includePartIds);
  const excludePartIds = normalizePartIds(edgeSettings?.excludePartIds);
  const focusedPartIds = normalizePartIds(edgeSettings?.focusedPartIds);
  const highlightPartIds = normalizePartIds(edgeSettings?.highlightPartIds);
  const edgeClassSettings = normalizeTopologyEdgeClassSettings(edgeSettings, baseTheme)
    .filter((classSetting) => (
      classSetting.classId === "feature" ||
      runtimeHasVisibilityClassRows(selectorRuntime)
    ));
  const visibilityClasses = edgeClassSettings.map((setting) => setting.classId);
  const edgeOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (baseTheme?.edgeOpacity ?? 0.84);
  const highlightOpacity = Number.isFinite(Number(edgeSettings?.highlightOpacity))
    ? clamp(Number(edgeSettings.highlightOpacity), 0, 1)
    : edgeOpacity;
  const dimmedOpacity = Number.isFinite(Number(edgeSettings?.dimmedOpacity))
    ? clamp(Number(edgeSettings.dimmedOpacity), 0, 1)
    : edgeOpacity;
  const thickness = Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : (baseTheme?.edgeThickness ?? 1);
  const baseOptions = {
    color: edgeSettings?.color || baseTheme?.edge || "#18181b",
    lineWidth: thickness,
    renderOrder: 3,
    depthTest: edgeSettings?.depthTest === false ? false : true,
    depthWrite: false,
    depthBias: topologyLineDepthBiasForWidth(thickness)
  };
  const createLine = (positions, options) => (
    createScreenSpaceLineSegments(context, positions, options, materials) ||
    createBasicLineSegments(context, positions, options)
  );
  const createLineStrip = (positions, options = {}) => {
    const lineWidth = Number.isFinite(Number(options.lineWidth)) ? Number(options.lineWidth) : 1;
    if (lineWidth <= 1.05) {
      return (
        createBasicLineStrip(context, positions, options) ||
        createScreenSpaceLineStrip(context, positions, options, materials)
      );
    }
    return (
      createScreenSpaceLineStrip(context, positions, options, materials) ||
      createBasicLineStrip(context, positions, options)
    );
  };
  const createClassGroup = (children) => {
    const lines = children.filter(Boolean);
    if (!lines.length) {
      return null;
    }
    if (lines.length === 1) {
      return lines[0];
    }
    const group = context.THREE ? new context.THREE.Group() : null;
    if (!group) {
      return lines[0];
    }
    for (const line of lines) {
      group.add(line);
    }
    return group;
  };
  const createLineStripGroup = (polylines, options) => {
    if (!context.THREE || !Array.isArray(polylines) || !polylines.length) {
      return null;
    }
    const positionValueCount = polylines.reduce((sum, positions) => sum + (positions?.length || 0), 0);
    if (
      polylines.length > MAX_TOPOLOGY_LINE_STRIP_POLYLINES ||
      positionValueCount > MAX_TOPOLOGY_LINE_STRIP_POSITION_VALUES
    ) {
      return null;
    }
    return createClassGroup(polylines.map((positions) => createLineStrip(positions, options)));
  };
  const createClassLine = (classSetting, options = {}) => {
    const lineWidth = Number.isFinite(Number(options.lineWidth))
      ? Number(options.lineWidth)
      : classSetting.thickness;
    const filters = {
      includePartIds: options.includePartIds || includePartIds,
      excludePartIds: options.excludePartIds || excludePartIds,
      visibilityClasses: [classSetting.classId]
    };
    const lineOptions = {
      ...baseOptions,
      ...options,
      lineWidth,
      opacity: Number.isFinite(Number(options.opacity)) ? options.opacity : classSetting.opacity,
      depthBias: Number.isFinite(Number(options.depthBias))
        ? options.depthBias
        : topologyLineDepthBiasForWidth(lineWidth, { visibilityClass: classSetting.classId })
    };
    const polylines = shouldBuildTopologyLineStrips(selectorRuntime, filters)
      ? buildTopologyDisplayEdgePolylines(selectorRuntime, filters)
      : [];
    const stripGroup = createLineStripGroup(polylines, lineOptions);
    if (stripGroup) {
      return stripGroup;
    }
    const positions = buildTopologyDisplayEdgePositions(selectorRuntime, {
      ...filters
    });
    if (!positions?.length) {
      return null;
    }
    return createLine(positions, lineOptions);
  };

  if (highlightPartIds.length) {
    const positions = buildTopologyDisplayEdgePositions(selectorRuntime, {
      includePartIds: highlightPartIds,
      visibilityClasses
    });
    if (!positions?.length) {
      return null;
    }
    const line = createLine(positions, {
      ...baseOptions,
      color: edgeSettings?.highlightColor || baseOptions.color,
      opacity: highlightOpacity,
      depthBias: Number.isFinite(Number(edgeSettings?.highlightDepthBias))
        ? clamp(Number(edgeSettings.highlightDepthBias), 0, 0.01)
        : 0,
      renderOrder: Number.isFinite(Number(edgeSettings?.highlightRenderOrder))
        ? Number(edgeSettings.highlightRenderOrder)
        : 26
    });
    if (line) {
      line.name = "TopologyDisplayEdgeHighlights";
      line.userData.partId = "__topology_highlight__";
    }
    return line;
  }

  if (focusedPartIds.length && context.THREE) {
    const group = new context.THREE.Group();
    for (const classSetting of edgeClassSettings) {
      const dimmedLine = createClassLine(classSetting, {
        excludePartIds: focusedPartIds,
        opacity: Math.min(dimmedOpacity, classSetting.opacity),
        renderOrder: 3
      });
      const focusedLine = createClassLine(classSetting, {
        includePartIds: focusedPartIds,
        opacity: classSetting.opacity,
        renderOrder: 4
      });
      if (dimmedLine) {
        group.add(dimmedLine);
      }
      if (focusedLine) {
        group.add(focusedLine);
      }
    }
    if (!group.children.length) {
      return null;
    }
    group.name = "TopologyDisplayEdges";
    group.userData.partId = "__topology__";
    return group;
  }

  const classLines = edgeClassSettings.map((classSetting) => createClassLine(classSetting));
  const line = createClassGroup(classLines);
  if (!line) {
    return null;
  }
  line.name = "TopologyDisplayEdges";
  line.userData.partId = "__topology__";
  return line;
}
