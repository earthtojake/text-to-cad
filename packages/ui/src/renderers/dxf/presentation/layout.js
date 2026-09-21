import { buildDxfPreviewMeshData, extractDxfScorePolylines } from "@hardcore/core/lib/dxf/buildPreviewMesh.js";
import {
  dxfBendGuideSegments, dxfFlatPatternExtents, foldDxfPoint, normalizeDxfFoldOptions, transformDxfPreviewPositions
} from "@hardcore/core/lib/dxf/foldPreview.js";
import { DXF_PREVIEW_REFERENCE_THICKNESS_MM, dxfPreviewPositionsMm } from "@hardcore/core/lib/dxf/previewGlb.js";
import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";
import { createDxfTextMarkings } from "../dxfTextMarkings.js";
import { normalizeDxfBendAngleDeg, normalizeDxfOrientation, normalizeDxfThicknessMm } from "../dxfSettings.js";

// Theme-independent inks, chosen to read on a light and a dark stage alike.
const SCORE_INK = 0x8a93a3;
const GUIDE_INK = 0x5f6775;
const DEFAULT_TEXT_INK = "#8a93a3";
// How far above the folded top face the annotations sit, in mm of the FOLDED part.
const OVERLAY_ELEVATION_MM = 0.3;
// The mesher reads <= 0 as "use the drawing default" (2 mm); a hair keeps the 0 mm setting
// meaning FLAT-thin rather than jumping to that default.
const MIN_MESHED_THICKNESS_MM = 0.05;

const boundsOfSoup = (positions) => {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[index + axis];
      if (value < min[axis]) min[axis] = value;
      if (value > max[axis]) max[axis] = value;
    }
  }
  return Number.isFinite(min[0]) ? { min, max } : { min: [0, 0, 0], max: [0, 0, 0] };
};

// Mesher space is Y-up; the scene is CAD Z-up. (x, y, z) -> (x, z, -y), a rotation about X
// with determinant +1. Handedness is not academic: the mirrored alternatives are invisible on
// a symmetric plate and obvious the moment the profile is lettering.
function toCadSpace(source) {
  const mapped = new Float32Array(source.length);
  for (let index = 0; index < source.length; index += 3) {
    mapped[index] = source[index];
    mapped[index + 1] = source[index + 2];
    mapped[index + 2] = -source[index + 1];
  }
  return mapped;
}

/** Post-fold orientation: quarter-turns about each world axis, about the flat pattern's own
 *  centre so the reoriented part stays where the camera is looking. Exact by construction
 *  (sin/cos of k*90° are integers). Null when there is nothing to turn. */
function orientationTransform(THREE, orientation, flat) {
  const turns = normalizeDxfOrientation(orientation);
  if (!turns.x && !turns.y && !turns.z) return null;
  const e = new THREE.Matrix4().makeRotationFromEuler(
    new THREE.Euler((turns.x * Math.PI) / 2, (turns.y * Math.PI) / 2, (turns.z * Math.PI) / 2, "XYZ")
  ).elements;
  let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
  for (let index = 0; index < flat.length; index += 3) {
    const x = flat[index];
    const y = flat[index + 1];
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const center = [(minX + maxX) / 2, (minY + maxY) / 2, 0];
  const point = ([px, py, pz]) => {
    const x = px - center[0];
    const y = py - center[1];
    const z = pz - center[2];
    return [
      e[0] * x + e[4] * y + e[8] * z + center[0],
      e[1] * x + e[5] * y + e[9] * z + center[1],
      e[2] * x + e[6] * y + e[10] * z + center[2]
    ];
  };
  return {
    point,
    buffer(array) {
      for (let index = 0; index < array.length; index += 3) {
        const [x, y, z] = point([array[index], array[index + 1], array[index + 2]]);
        array[index] = x;
        array[index + 1] = y;
        array[index + 2] = z;
      }
      return array;
    }
  };
}

/** The dxf with every record on a hidden layer dropped, or the dxf itself when none is. */
function geometryWithoutLayers(dxf, hidden) {
  if (!hidden.size || !dxf?.geometry) return dxf;
  const keep = records => (Array.isArray(records) ? records.filter(record => !hidden.has(record?.layer)) : []);
  return {
    ...dxf,
    geometry: {
      lines: keep(dxf.geometry.lines), arcs: keep(dxf.geometry.arcs),
      circles: keep(dxf.geometry.circles), texts: keep(dxf.geometry.texts)
    }
  };
}

/**
 * The LAYOUT presentation: a cut layout's closed contours extruded into a flat pattern, plus
 * the drawing's annotations on its top face.
 *
 * The prism is baked ONCE at 1 mm, so thickness is a scale on a cached buffer rather than a
 * re-mesh, and a boxed fold is a vertex rewrite of the same buffer. A curved fold, and a
 * hidden cut layer, are the two things only a fresh mesh can express; that mesh is swapped
 * into the same sheet object. The dashed creases, score lines and text markings all ride the
 * same fold chain as the sheet, so they stay on the faces they annotate.
 *
 * All the geometry maths is core's (`lib/dxf/*`), shared verbatim with the headless snapshot
 * builder. What is here is the objects, and what a setting change does to them.
 *
 * @param {typeof import("three")} THREE
 * @param {object} dxf  `parseDxf` output, in millimetres.
 * @param {{ bendLines: { start: number[], end: number[] }[], layerKinds: Map<string, string>,
 *   layerColors: Map<string, string> }} facts  What the scene read off the parse once.
 * @returns {import("./presentation.js").DxfPresentation}
 * @throws when the contours will not mesh — the caller falls back to the document presentation.
 */
export function createDxfLayoutPresentation(THREE, dxf, { bendLines, layerKinds, layerColors }) {
  const flat = dxfPreviewPositionsMm(buildDxfPreviewMeshData(dxf, DXF_PREVIEW_REFERENCE_THICKNESS_MM, null));
  if (!flat.length) throw new Error("This DXF has no closed cut contour to extrude.");

  const root = new THREE.Group();
  root.name = "dxf-layout";
  const flatGeometry = new THREE.BufferGeometry();
  // The presentation owns this copy: the fold always writes from `flat`, never from the pose.
  flatGeometry.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(flat), 3));
  const sheetMaterial = new THREE.MeshPhysicalMaterial({ color: 0xffffff, side: THREE.DoubleSide });
  // Nothing in a DXF says what colour the stock is, so the sheet takes the viewer's surface
  // colour — unless the Material preset tints it.
  sheetMaterial.userData.cadSourceColor = false;
  const sheet = new THREE.Mesh(flatGeometry, sheetMaterial);
  sheet.name = "dxf-sheet";
  sheet.castShadow = true;
  root.add(sheet);
  const look = createSurfaceLook(THREE, sheet);
  const texts = createDxfTextMarkings(THREE);
  root.add(texts.group);

  let curvedGeometry = null;
  let guides = null;
  let scores = null;
  let currentLook = null;
  let tintHex = null;
  let disposed = false;

  const dressSheet = () => {
    // A DXF authors no finish and no colour: the sheet is stock, not a painted part. So
    // Render is a look like any other — the studio's surface over the viewer's own fill —
    // never a finish "kept", which would leave the sheet the bare white it was built with.
    look.apply(currentLook ? { ...currentLook, authored: false } : null);
    if (!tintHex) return;
    // Today's precedence, kept: a Material preset beats every colour mode. The viewer lifts a
    // surface by a trace of its own colour, so a tinted sheet lifts by its tint.
    const material = sheet.material;
    material.color.set(tintHex);
    if (material.emissive && material.emissiveIntensity > 0) material.emissive.set(tintHex);
  };
  const ensureGuides = (span) => {
    if (guides) return guides;
    guides = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineDashedMaterial({
      color: GUIDE_INK, dashSize: span / 24, gapSize: span / 36, transparent: true, opacity: 0.9, depthWrite: false
    }));
    guides.name = "dxf-bend-guides";
    guides.frustumCulled = false;
    root.add(guides);
    return guides;
  };
  const ensureScores = () => {
    if (scores) return scores;
    scores = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({
      color: SCORE_INK, transparent: true, opacity: 0.95, depthWrite: false
    }));
    scores.name = "dxf-score-lines";
    scores.frustumCulled = false;
    root.add(scores);
    return scores;
  };

  return {
    kind: "layout",
    object3D: root,
    restBounds: boundsOfSoup(flat),
    setSurfaceLook(next) {
      if (disposed) return;
      currentLook = next;
      dressSheet();
    },
    update(settings) {
      if (disposed) return;
      const hidden = new Set(Array.isArray(settings.hiddenLayers) ? settings.hiddenLayers : []);
      if (tintHex !== (settings.tintHex || null)) {
        tintHex = settings.tintHex || null;
        dressSheet();
      }

      const thicknessMm = normalizeDxfThicknessMm(settings.thicknessMm);
      const bends = Array.isArray(settings.bends) ? settings.bends : [];
      const foldOptions = {
        bendLines: bendLines.length ? bendLines : null,
        bendAxesX: [],
        bendAnglesRad: bends.map(bend => (normalizeDxfBendAngleDeg(bend?.angleDeg) * Math.PI / 180)
          * (bend?.direction === "down" ? -1 : 1)),
        thicknessScale: thicknessMm / DXF_PREVIEW_REFERENCE_THICKNESS_MM
      };
      const orient = orientationTransform(THREE, settings.orientation, flat);
      const anyAngle = foldOptions.bendAnglesRad.some(angle => angle !== 0);
      const anyCutLayerHidden = [...hidden].some(name => layerKinds.get(name) === "cut");
      const effective = geometryWithoutLayers(dxf, hidden);
      // Hiding a cut layer changes the SOLID, which only a live re-mesh can express: the baked
      // prism has the hidden geometry welded in. Its bends then render curved too — the mesher
      // has one bend geometry.
      const curvedRequested = (settings.bendStyle === "curved" && bendLines.length > 0 && anyAngle) || anyCutLayerHidden;

      let guideSegments = null;
      let curved = null;
      if (curvedRequested) {
        try {
          // Direction flips on the way in: the mesher bends toward ITS +Y, and (x, y, z) ->
          // (x, z, -y) sends mesher +Y to CAD -Z, so handing it the opposite direction is what
          // makes the UI's "Up" fold up on screen. guideElevationSign -1 for the same reason.
          curved = buildDxfPreviewMeshData(effective, Math.max(thicknessMm, MIN_MESHED_THICKNESS_MM),
            bends.map(bend => ({ angleDeg: bend?.angleDeg, direction: bend?.direction === "down" ? "up" : "down" })),
            { guideElevationSign: -1, bendInsideRadiusMm: settings.bendRadiusMm, bendKFactor: settings.kFactor });
        } catch {
          // A drawing the bend mesher cannot band (a hole crossing a bend region) falls back to
          // the sharp fold rather than rendering nothing.
          curved = null;
        }
      }

      if (curved) {
        const positions = orient ? orient.buffer(toCadSpace(curved.vertices)) : toCadSpace(curved.vertices);
        curvedGeometry ||= new THREE.BufferGeometry();
        curvedGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        curvedGeometry.setIndex(new THREE.BufferAttribute(curved.indices, 1));
        // Drop the old normals FIRST: computeVertexNormals reuses an existing normal attribute,
        // and every re-mesh changes the vertex count (each bend's band adds vertices). A stale
        // buffer makes the draw fail outright and silently — a four-bend panel goes blank on
        // the fourth bend while three stay under the count and look fine.
        curvedGeometry.deleteAttribute("normal");
        curvedGeometry.computeVertexNormals();
        curvedGeometry.computeBoundingBox();
        curvedGeometry.computeBoundingSphere();
        sheet.geometry = curvedGeometry;
        const source = curved.guide_line_segments;
        if (source?.length) guideSegments = orient ? orient.buffer(toCadSpace(source)) : toCadSpace(source);
      } else {
        const position = flatGeometry.getAttribute("position");
        transformDxfPreviewPositions(flat, position.array, foldOptions);
        if (orient) orient.buffer(position.array);
        position.needsUpdate = true;
        // A non-indexed soup: per-face normals, which is what the folded sheet wants.
        flatGeometry.computeVertexNormals();
        flatGeometry.computeBoundingBox();
        flatGeometry.computeBoundingSphere();
        sheet.geometry = flatGeometry;
      }

      // The dashed creases. Hiding a bend layer hides them too — the marks ARE that layer.
      const bendLayerHidden = [...hidden].some(name => layerKinds.get(name) === "bend");
      const segments = bendLayerHidden ? new Float32Array(0)
        : guideSegments || (bendLines.length ? (orient
          ? orient.buffer(dxfBendGuideSegments(flat, foldOptions))
          : dxfBendGuideSegments(flat, foldOptions)) : new Float32Array(0));
      if (segments.length) {
        const extents = dxfFlatPatternExtents(flat);
        const object = ensureGuides(Math.max(extents.yMax - extents.yMin, 1));
        object.geometry.setAttribute("position", new THREE.BufferAttribute(segments, 3));
        object.computeLineDistances();
        object.geometry.computeBoundingSphere();
        object.visible = true;
      } else if (guides) guides.visible = false;

      // SCORE LINES and TEXT MARKINGS, on the sheet's top face and folded through the same
      // chain. In curved mode that chain is the vertex fold, so a score crossing a bend band
      // chords across the arc — accepted: annotations rarely sit inside a bend.
      const fold = normalizeDxfFoldOptions(foldOptions);
      const zTop = dxfFlatPatternExtents(flat).zMax + OVERLAY_ELEVATION_MM / Math.max(fold.scale, 1e-6);
      const place = ([x, y]) => {
        const point = foldDxfPoint(x, y, zTop, fold);
        return orient ? orient.point(point) : point;
      };
      let scoreValues = [];
      try {
        for (const polyline of extractDxfScorePolylines(effective)) {
          for (let index = 0; index < polyline.length - 1; index += 1) {
            scoreValues.push(...place(polyline[index]), ...place(polyline[index + 1]));
          }
        }
      } catch { scoreValues = []; }
      if (scoreValues.length) {
        const object = ensureScores();
        object.geometry.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(scoreValues), 3));
        object.geometry.computeBoundingSphere();
        object.visible = true;
      } else if (scores) scores.visible = false;

      const markings = (Array.isArray(effective?.geometry?.texts) ? effective.geometry.texts : [])
        .map(text => ({ ...text, colorHex: layerColors.get(text.layer) || DEFAULT_TEXT_INK }));
      texts.update(markings, (marking, size) => {
        const rotation = ((Number(marking.rotationDeg) || 0) * Math.PI) / 180;
        const ex = [Math.cos(rotation), Math.sin(rotation)];
        const ey = [-Math.sin(rotation), Math.cos(rotation)];
        // The DXF anchor is baseline-left; the plane's centre sits half a width along the text
        // direction and a little above the baseline. All in FLAT coords, then folded.
        const center = [
          marking.position[0] + ex[0] * (size.width / 2) + ey[0] * (size.height * 0.22),
          marking.position[1] + ex[1] * (size.width / 2) + ey[1] * (size.height * 0.22)
        ];
        const step = 0.5;
        const origin = place(center);
        const alongX = place([center[0] + ex[0] * step, center[1] + ex[1] * step]);
        const alongY = place([center[0] + ey[0] * step, center[1] + ey[1] * step]);
        const basisX = new THREE.Vector3(alongX[0] - origin[0], alongX[1] - origin[1], alongX[2] - origin[2]).normalize();
        const basisY = new THREE.Vector3(alongY[0] - origin[0], alongY[1] - origin[1], alongY[2] - origin[2]).normalize();
        const basisZ = new THREE.Vector3().crossVectors(basisX, basisY).normalize();
        return { position: origin, basis: new THREE.Matrix4().makeBasis(basisX, basisY, basisZ) };
      });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      look.dispose();
      texts.dispose();
      sheetMaterial.dispose();
      flatGeometry.dispose();
      curvedGeometry?.dispose();
      for (const object of [guides, scores]) {
        object?.geometry.dispose();
        object?.material.dispose();
      }
    }
  };
}
