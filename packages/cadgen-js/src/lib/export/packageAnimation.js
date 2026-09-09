// A clip, sampled into glTF node animation: the export half of choreography.
//
// The viewer and the video renderer DRIVE a clip — evaluate it every frame and
// push the result through the effects pass. A GLB carries no evaluator, so an
// exported clip has to become data: per-occurrence TRS keyframes on a shared
// time line, baked at the schedule framePlan resolves. Everything here is the
// translation between those two worlds, and its whole job is to make the
// translation HONEST — a clip drives five kinds of effect and glTF nodes carry
// two of them, so the three it cannot carry are refused by name rather than
// dropped into a file that looks finished and moves wrong.
//
// What maps, and how:
//
//   .rotate / .translate  exact. The composed per-occurrence matrix is rigid,
//                         so it decomposes to translation + quaternion with no
//                         residue, and the pivot a rotation was taken about
//                         comes back as the translation half of that pair.
//   .opacity              no standard animated channel exists. Refused unless
//                         the caller drops it, and then baked STATIC at `start`
//                         as a material alpha.
//   .visible              same: refused, or dropped by omitting the occurrence.
//   .deformTube           per-VERTEX motion, not a node transform. The `deform`
//                         mode decides; see sampleClipAnimation.
//
// This module is PURE: no filesystem, no glTF writing. It reads a package
// descriptor for the occurrence table the clip resolves labels against (the
// same table meshData.js composes for the viewer, so `m.get("forearm")` names
// the same occurrence in an export as it does on screen), and returns tracks
// the GLB writer turns into accessors.

import { Matrix4, Quaternion, Vector3 } from "three";

import { evaluateAnimationClip } from "../../common/animationRuntime.js";
import { framePlanElapsedSec } from "../../common/framePlan.js";
import { sameTubeRestShape } from "../../common/tubeDeformation.js";

// The clip runtime takes its matrix classes as an argument rather than
// importing them, so the export path drives it with the SAME three the viewer
// does: a second matrix implementation here would be a second answer to
// "where does this part end up", and the two would agree until they did not.
const CLIP_THREE = { Matrix4, Vector3 };

/** Effects a caller may bake STATIC instead of having the export refuse them. */
export const ANIMATION_DROPPABLE_EFFECTS = Object.freeze(["opacity", "visible"]);

/** What `deform` may say about a clip that deforms tube geometry. */
export const ANIMATION_DEFORM_MODES = Object.freeze(["refuse", "morph", "rest"]);

// How much finer than the export's own frame rate a morph bake MEASURES its fit on.
//
// Morph weights interpolate the RESULT of two poses; the clip interpolates its own
// control numbers and rebuilds the path from them, and the path -> vertex map (arc-
// length reparameterisation, transported frames, stretch) is not linear. The two
// therefore agree only AT sampled instants, and a fit measured on the export frame
// grid certifies nothing about the motion between export frames -- which is most of
// the playback. Measuring 4x finer bounds the between-grid residual at about 1/16 of
// the adjacent-sample one, because the error is ordinary chord error and falls as
// dt^2. The floor keeps a low-fps request (an 8 fps preview) from certifying itself
// on an 8 Hz grid.
export const MORPH_FIT_GRID_MULTIPLE = 4;
export const MORPH_FIT_GRID_MIN_HZ = 96;

/** The sampling grid a morph bake FITS on, as a whole multiple of the export's fps.
 *
 * A whole multiple, so every export frame IS a grid sample and one pass over the
 * grid serves both the TRS keyframes and the deformation fit. */
export function morphFitGrid(plan) {
  const multiple = Math.max(MORPH_FIT_GRID_MULTIPLE, Math.ceil(MORPH_FIT_GRID_MIN_HZ / plan.fps));
  return {
    multiple,
    hz: plan.fps * multiple,
    count: (plan.frameCount - 1) * multiple + 1,
  };
}

// glTF is Y-up metres; a package is Z-up CAD millimetres, and
// packageMeshExport's yUpPrimitives rotates the VERTICES on the way out:
// (x, y, z) -> (x, z, -y), mm -> m. A clip's matrix is authored in the CAD
// space those vertices left behind, so it has to be carried across the same
// change of basis — C M C-inverse — or a rotation about Z would come out of the
// file as a rotation about Y. The uniform scale cancels in the linear part and
// survives only in the translation, which is exactly right: an occurrence that
// travels 40 mm travels 0.04 m.
const CAD_TO_GLB_SCALE = 0.001;

function cadToGlbBasis() {
  return new Matrix4().set(
    CAD_TO_GLB_SCALE, 0, 0, 0,
    0, 0, CAD_TO_GLB_SCALE, 0,
    0, -CAD_TO_GLB_SCALE, 0, 0,
    0, 0, 0, 1,
  );
}

function glbToCadBasis() {
  const inverse = 1 / CAD_TO_GLB_SCALE;
  return new Matrix4().set(
    inverse, 0, 0, 0,
    0, 0, -inverse, 0,
    0, inverse, 0, 0,
    0, 0, 0, 1,
  );
}

// A matrix a clip composed out of rotations and translations only; anything
// this far from identity in any element is real motion. The tolerance is
// slack enough to absorb the trig of a full turn (makeRotationAxis at 360°
// lands ~1e-16 off) and far tighter than any motion worth a keyframe.
const IDENTITY_EPSILON = 1e-12;
const IDENTITY_ELEMENTS = new Matrix4().elements;

function isIdentityMatrix(matrix) {
  const elements = matrix.elements;
  for (let index = 0; index < 16; index += 1) {
    if (Math.abs(elements[index] - IDENTITY_ELEMENTS[index]) > IDENTITY_EPSILON) {
      return false;
    }
  }
  return true;
}

/** The occurrence table a clip resolves `m.get(...)` against.
 *
 * The shape is meshData's — `parts` with `id` and `label` — because that is
 * what `createAnimationFrame` indexes, and building it any other way here would
 * let an export resolve a label the viewer does not. Mirrors
 * buildComposedPackageMeshData's naming: the id is the occurrence id (the
 * component id when an occurrence has none), the label its display name.
 */
export function animationTargetsFromDescriptor(descriptor) {
  const parts = [];
  for (const occurrence of descriptor?.occurrences || []) {
    const occurrenceId = String(occurrence?.id || "").trim();
    const componentId = String(occurrence?.component || "").trim();
    const id = occurrenceId || componentId;
    if (!id) {
      continue;
    }
    const name = String(occurrence?.name || occurrenceId || componentId).trim();
    parts.push({ id, occurrenceId: id, componentId, name, label: name });
  }
  return { parts };
}

function summarize(ids, limit = 6) {
  const sorted = [...ids].sort();
  if (sorted.length <= limit) {
    return sorted.join(", ");
  }
  return `${sorted.slice(0, limit).join(", ")} (and ${sorted.length - limit} more)`;
}

function newTrack(sampleCount) {
  const track = {
    translations: [],
    rotations: [],
    scales: [],
    count: 0,
  };
  // Frames before an occurrence first MOVED are frames it sat at rest, and the
  // rest pose is the geometry as baked: identity, not a missing sample. A
  // channel with a hole in it interpolates across the hole.
  for (let index = 0; index < sampleCount; index += 1) {
    appendSample(track, null);
  }
  return track;
}

const SAMPLE_TRANSLATION = new Vector3();
const SAMPLE_ROTATION = new Quaternion();
const SAMPLE_SCALE = new Vector3();

// `null` is the REST sample: the geometry as baked, which is identity. It takes
// the same hemisphere alignment as every other sample rather than short-circuiting
// past it -- a clip that stops touching an occurrence after turning it past 180°
// hands the rest sample a previous quaternion in the far hemisphere, and the pair
// (q, identity) is the sign flip this alignment exists to prevent.
function appendSample(track, matrix) {
  let tx = 0;
  let ty = 0;
  let tz = 0;
  let x = 0;
  let y = 0;
  let z = 0;
  let w = 1;
  let sx = 1;
  let sy = 1;
  let sz = 1;
  if (matrix !== null) {
    matrix.decompose(SAMPLE_TRANSLATION, SAMPLE_ROTATION, SAMPLE_SCALE);
    ({ x: tx, y: ty, z: tz } = SAMPLE_TRANSLATION);
    ({ x, y, z, w } = SAMPLE_ROTATION);
    ({ x: sx, y: sy, z: sz } = SAMPLE_SCALE);
  }
  if (track.count > 0) {
    // q and -q are the same rotation but not the same four numbers, and glTF
    // interpolates the numbers: a sign flip between two keyframes sends the
    // occurrence the long way round in one frame. Keep every sample in the
    // hemisphere of the one before it.
    const base = (track.count - 1) * 4;
    const dot = track.rotations[base] * x
      + track.rotations[base + 1] * y
      + track.rotations[base + 2] * z
      + track.rotations[base + 3] * w;
    if (dot < 0) {
      x = -x; y = -y; z = -z; w = -w;
    }
  }
  track.translations.push(tx, ty, tz);
  track.rotations.push(x, y, z, w);
  track.scales.push(sx, sy, sz);
  track.count += 1;
}

// Whether a track carries MOTION or just an offset. Compared as float32,
// because that is what the file stores: a track whose samples all round to the
// same four bytes would be a channel that animates nothing, and the offset it
// does carry belongs on the node's own transform instead.
function varies(values, stride, count) {
  for (let sample = 1; sample < count; sample += 1) {
    for (let component = 0; component < stride; component += 1) {
      if (Math.fround(values[sample * stride + component]) !== Math.fround(values[component])) {
        return true;
      }
    }
  }
  return false;
}

function scaleIsUnit(scales, count) {
  for (let index = 0; index < count * 3; index += 1) {
    if (Math.fround(scales[index]) !== 1) {
      return false;
    }
  }
  return true;
}

/** Sample one clip over one frame plan into per-occurrence TRS tracks.
 *
 * Returns `{ times, channels, rest, statics, warnings }`:
 *
 * - `times` — one shared Float32Array, `index / fps`. The exported animation is
 *   re-based to zero: `start` says where in the CLIP the span begins, and a
 *   file that carried that offset would open with a stretch of nothing before
 *   anything moved.
 * - `channels` — one per occurrence whose transform CHANGES over the span.
 * - `rest` — every touched occurrence's transform at the first sample, so the
 *   file shows the clip's opening pose when nothing is playing it.
 * - `statics` — `{ opacity: Map, hidden: Set }`, the dropped effects baked at
 *   `start`.
 *
 * `deform` decides what a clip that deforms tube geometry does here.
 * `"refuse"` (the default) stops the export: a hand whose tendons silently
 * froze is exactly the file this door exists not to write. `"rest"` ships the
 * tubes at their rest shape and says so. `"morph"` collects the deformation at
 * every sample of the FIT GRID (4x the export fps, see morphFitGrid) into
 * `deformations`, which lib/export/packageTubeMorph.js turns into baked morph
 * targets — this module stays pure and geometry-free, so the clip is evaluated
 * exactly once per grid sample and the vertices are somebody else's problem.
 */
export function sampleClipAnimation(descriptor, clip, plan, { drop = [], deform = "refuse" } = {}) {
  const dropped = new Set(drop.map((name) => String(name).trim()));
  const unknownDrop = [...dropped].filter((name) => !ANIMATION_DROPPABLE_EFFECTS.includes(name));
  if (unknownDrop.length) {
    throw new Error(
      `animation drop names ${unknownDrop.sort().join(", ")}, which is not an effect this export `
      + `can bake static; droppable effects: ${ANIMATION_DROPPABLE_EFFECTS.join(", ")}`
    );
  }
  const deformMode = String(deform || "refuse");
  if (!ANIMATION_DEFORM_MODES.includes(deformMode)) {
    throw new Error(
      `animation deform must be one of ${ANIMATION_DEFORM_MODES.join(", ")}, got ${JSON.stringify(deform)}`
    );
  }

  const meshData = animationTargetsFromDescriptor(descriptor);
  const toGlb = cadToGlbBasis();
  const fromGlb = glbToCadBasis();
  const posed = new Matrix4();

  const tracks = new Map();
  const opacityAt = new Map();
  const hiddenAt = new Set();
  const opacityIds = new Set();
  const visibleIds = new Set();
  const deformedIds = new Set();
  const deformations = new Map();
  const braidIds = new Set();

  // ONE pass. Under morph the clip is evaluated on the finer FIT grid and the
  // TRS/style work runs on the whole-numbered sub-multiple of it — every export
  // frame is a grid sample by construction — so a morph bake costs one clip
  // evaluation per grid sample rather than two passes over two schedules. With
  // no morph the grid IS the frame schedule and this loop is the old one.
  const grid = deformMode === "morph"
    ? morphFitGrid(plan)
    : { multiple: 1, hz: plan.fps, count: plan.frameCount };

  for (let gridIndex = 0; gridIndex < grid.count; gridIndex += 1) {
    // Through framePlan's own arithmetic at a FRACTIONAL frame ordinal, never a
    // second derivation of it: where the samples fall is the one thing the video
    // renderer and this export must not disagree about.
    const elapsed = framePlanElapsedSec(plan, gridIndex / grid.multiple);
    const frame = evaluateAnimationClip(CLIP_THREE, meshData, clip, elapsed);
    const index = gridIndex % grid.multiple === 0 ? gridIndex / grid.multiple : -1;
    if (index >= 0) {
      for (const [partId, matrix] of frame.matrices) {
        let track = tracks.get(partId);
        if (!track) {
          if (isIdentityMatrix(matrix)) {
            continue;
          }
          track = newTrack(index);
          tracks.set(partId, track);
        }
        posed.multiplyMatrices(toGlb, matrix).multiply(fromGlb);
        appendSample(track, posed);
      }
      // An occurrence with a track the clip did not touch THIS frame is back at
      // rest for it, which is a sample, not a gap.
      for (const track of tracks.values()) {
        if (track.count === index) {
          appendSample(track, null);
        }
      }
      for (const [partId, style] of frame.styles) {
        if (style && Object.hasOwn(style, "opacity")) {
          opacityIds.add(partId);
          if (index === 0) {
            opacityAt.set(partId, style.opacity);
          }
        }
        if (style && Object.hasOwn(style, "visible")) {
          visibleIds.add(partId);
          if (index === 0 && style.visible === false) {
            hiddenAt.add(partId);
          }
        }
      }
    }
    for (const [partId, deformation] of frame.deformations) {
      deformedIds.add(partId);
      if (deformation.braid) {
        braidIds.add(partId);
      }
      if (deformMode !== "morph") {
        continue;
      }
      let entry = deformations.get(partId);
      if (!entry) {
        // The tube's FIRST deformation, kept whole: it is both the rest shape every
        // later sample is checked against and the one copy of that rest spec the
        // whole clip shares. Compared by value rather than through a key string,
        // because a key per tube per grid sample is thousands of samples' worth of
        // garbage for an answer the numbers already give.
        entry = { rest: deformation, samples: [] };
        deformations.set(partId, entry);
      } else if (!sameTubeRestShape(entry.rest, deformation)) {
        // One base mesh per occurrence is what a morph target IS — deltas against
        // a shape the file states once. A clip that re-routes a tendon mid-span
        // has no such shape, and blending toward one that was never the rest of
        // this pose would bend the cord through the hand. Refuse by name.
        throw new Error(
          `clip ${clip.id} changes the REST path of ${partId} at ${elapsed.toFixed(4)}s, so its `
          + "geometry has no single base mesh for morph targets to be deltas against. Author "
          + "one rest path per tube for the whole clip (move the tube with .translate/.rotate "
          + `instead), or export the clip as video (cadgen step snapshot --animation ${clip.id} `
          + "--video)"
        );
      }
      // The rest spec is constant for the whole clip — the refusal directly above is
      // what guarantees it — so every sample shares the tube's ONE copy instead of
      // retaining its own. By value this is a no-op; in memory it is half the grid.
      entry.samples.push({
        index: gridIndex,
        timeSec: gridIndex / grid.hz,
        deformation: deformation === entry.rest
          ? deformation
          : { ...deformation, restSpec: entry.rest.restSpec },
      });
    }
  }

  const warnings = [];
  for (const effect of ANIMATION_DROPPABLE_EFFECTS) {
    const ids = effect === "opacity" ? opacityIds : visibleIds;
    if (!ids.size) {
      continue;
    }
    if (!dropped.has(effect)) {
      throw new Error(
        `clip ${clip.id} animates .${effect}() on ${summarize(ids)}, and glTF has no standard `
        + `animated channel for it. Pass drop: ["${effect}"] to bake the value at start into the `
        + "file instead, or animate the occurrence's transform rather than its appearance"
      );
    }
    warnings.push(
      `.${effect}() is not an animated glTF channel: ${summarize(ids)} carries its value at `
      + "start, frozen for the whole clip"
    );
  }
  if (deformedIds.size) {
    if (deformMode === "refuse") {
      throw new Error(
        `clip ${clip.id} deforms tube geometry on ${summarize(deformedIds)}: that is per-vertex `
        + "motion, which a node transform cannot carry. Pass deform: \"morph\" to bake it as "
        + "morph targets (bigger file, deformTolerance sets how close they track), deform: "
        + "\"rest\" to ship those tubes at their rest shape knowing they do not move, or export "
        + `the clip as video (cadgen step snapshot --animation ${clip.id} --video)`
      );
    }
    if (deformMode === "morph") {
      if (braidIds.size) {
        // The braid is a FRAGMENT SHADER over a per-vertex material coordinate
        // (common/tubeBraidMaterial.js), not geometry, and glTF has nowhere to put
        // it. The cord's shape and motion export exactly; its woven surface does
        // not, so it exports smooth. Said out loud every time, because the only
        // other way to find out is to compare a screenshot.
        warnings.push(
          `${summarize(braidIds)} carries a braid: the strand pattern is a shader, not geometry, `
          + "so the exported cord has the right shape and motion and a smooth surface"
        );
      }
      warnings.push(
        "morph targets carry the tube deformation as per-vertex keyframes; cadgen's own CAD "
        + "Viewer reads a GLB's geometry and ignores its glTF animation, so play this file in "
        + "Blender, a three.js viewer or a browser model preview"
      );
    } else {
      warnings.push(
        `deform: "rest" ships ${summarize(deformedIds)} at rest shape: the clip's tube deformation `
        + "is per-vertex motion this file does not carry"
      );
    }
  }

  // An occurrence `drop: ["visible"]` hid is not in the file at all — the mesh
  // build skips its primitives, so no node is written for it — and a channel
  // targeting a node no primitive declared is the glTF writer's last-resort
  // throw. That throw is reachable through the escape hatch the visibility
  // refusal itself hands out (a reveal clip hides an occurrence at `start` and
  // moves it), so the conflict is settled here, where the clip is named and the
  // drop was asked for. The motion is unobservable either way; what would be
  // dishonest is not saying it was left out.
  const hiddenAndMoving = [...hiddenAt].filter((partId) => tracks.has(partId));
  if (hiddenAndMoving.length) {
    for (const partId of hiddenAndMoving) {
      tracks.delete(partId);
    }
    warnings.push(
      `${summarize(hiddenAndMoving)} moves in this clip and is hidden at start: dropping `
      + ".visible() omits the occurrence from the file, and a node that is not there carries "
      + "no motion"
    );
  }

  const times = new Float32Array(plan.frameCount);
  for (let index = 0; index < plan.frameCount; index += 1) {
    times[index] = index / plan.fps;
  }

  const channels = [];
  const rest = new Map();
  for (const [occurrenceId, track] of tracks) {
    const translations = new Float32Array(track.translations);
    const rotations = new Float32Array(track.rotations);
    const scales = new Float32Array(track.scales);
    const unitScale = scaleIsUnit(scales, track.count);
    rest.set(occurrenceId, {
      translation: [translations[0], translations[1], translations[2]],
      rotation: [rotations[0], rotations[1], rotations[2], rotations[3]],
      scale: unitScale ? null : [scales[0], scales[1], scales[2]],
    });
    const channel = { node: occurrenceId };
    if (varies(translations, 3, track.count)) {
      channel.translation = translations;
    }
    if (varies(rotations, 4, track.count)) {
      channel.rotation = rotations;
    }
    // A clip built from .rotate/.translate never scales, so a scale channel is
    // normally pure waste; emitting one only when a sample actually scales
    // keeps that out of the file without letting a scaling matrix vanish.
    if (!unitScale && varies(scales, 3, track.count)) {
      channel.scale = scales;
    }
    // A constant offset is not motion: the node's own transform carries it (see
    // `rest`), and a channel of identical keyframes would only repeat it.
    if (channel.translation || channel.rotation || channel.scale) {
      channels.push(channel);
    }
  }
  // Deterministic bytes: occurrence order out of a Map is insertion order,
  // which is the order the clip happened to touch them in.
  channels.sort(compareChannels);

  return {
    name: clip.id,
    times,
    channels,
    rest,
    statics: { opacity: opacityAt, hidden: hiddenAt },
    // Empty unless `deform: "morph"`: the clip's tube deformation at every sample
    // of the fit grid, for packageTubeMorph to bake. Keyed by occurrence id, each
    // entry `{ rest, samples: [{ index, timeSec, deformation }] }` — `rest` the
    // tube's first deformation, whose rest spec every sample shares — with
    // `timeSec` already re-based to zero like `times` above.
    deformations,
    grid,
    warnings,
  };
}

// Deterministic bytes, and one place that decides the order: by node, then by
// KIND, so an occurrence that is both carried by a moving finger (a TRS channel)
// and deformed (a weights channel) writes the pair the same way round whichever
// the sampler happened to collect first.
function compareChannels(left, right) {
  if (left.node !== right.node) {
    return left.node < right.node ? -1 : 1;
  }
  return (left.weights ? 1 : 0) - (right.weights ? 1 : 0);
}

/** A sampled clip with baked morph-weight channels folded in.
 *
 * The sampler is geometry-free and cannot know how many targets a tube needed;
 * packageTubeMorph works that out and hands the channels back here, so the merge
 * and its ordering stay in the module that owns what a channel list means. */
export function withMorphChannels(sampled, morphChannels) {
  if (!morphChannels?.length) {
    return sampled;
  }
  return {
    ...sampled,
    channels: [...sampled.channels, ...morphChannels].sort(compareChannels),
  };
}

/** A sampled clip narrowed to the nodes the export actually wrote.
 *
 * The sampler resolves labels against the package DESCRIPTOR's occurrence table
 * — that is what makes `m.get("forearm")` mean the same thing here as on screen
 * — while the file's nodes are what actually TESSELLATED. An occurrence whose
 * component produced no triangles is in the first and not the second, and a
 * channel targeting a node no primitive declared is a hard throw out of
 * writeGlb: a glTF invariant reported to a user who asked about a clip. Settle
 * it here instead, and name what lost its motion.
 *
 * Pure, and a no-op in the ordinary case: the returned object is the one passed
 * in unless something actually had to go.
 */
export function restrictAnimationToNodes(sampled, nodeIds) {
  const missing = sampled.channels
    .map((channel) => channel.node)
    .filter((node) => !nodeIds.has(node));
  if (!missing.length) {
    return sampled;
  }
  const rest = new Map();
  for (const [node, pose] of sampled.rest) {
    if (nodeIds.has(node)) {
      rest.set(node, pose);
    }
  }
  return {
    ...sampled,
    channels: sampled.channels.filter((channel) => nodeIds.has(channel.node)),
    rest,
    warnings: [
      ...sampled.warnings,
      `${summarize(missing)} moves in this clip but has no geometry in the export, so the `
      + "file carries no node to animate for it",
    ],
  };
}
