// The choreography half: evaluate the clips a document's render module
// (`<name>.step.js`, loaded by renderModule.js) declares and drive raw
// per-occurrence transforms. Total independence by construction: this module
// knows nothing of mates, DOFs, presets, or the Pose tab; it targets
// occurrences by label and pushes matrices/styles through the same effects
// records the viewer already composes.
//
// Contract (the render module's `clips` export):
//   export const clips = {
//     demo: { label?, duration, loop?, update(t, m) { ... } },
//   };
// `update` is called every frame with t in seconds and m, the model handle.
// EVERY frame starts from rest: update(t) rebuilds state from scratch, so it
// must be a pure function of t — scrub, loop, and seek are free, and there is
// no persistent state to mutate.
//
// Handle API — m.get(target) returns an occurrence handle. A target is a
// LABEL (canonical), or an occurrence-id ref — "#o1.3.1", "o1.3.1", or a
// comma list "#o1.3.1,o1.3.2" — matching each id and everything beneath it
// (dotted-prefix containment):
//   .rotate(axisVec3, degrees, originVec3 = [0,0,0])
//   .translate(vec3)
//   .opacity(value 0..1)
//   .visible(bool)
// Successive transform calls PREMULTIPLY (later calls act in world space on
// the already-moved part): h.rotate(spin about own center) then
// h.rotate(orbit about the assembly origin) makes the spin ride the orbit.
// m.get() with an unknown label throws — a typo'd label must never silently
// animate nothing.

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

const DEG_TO_RAD = Math.PI / 180;

export function normalizeAnimationClips(rawClips) {
  const clips = {};
  for (const [id, raw] of Object.entries(isObject(rawClips) ? rawClips : {})) {
    if (!isObject(raw) || typeof raw.update !== "function") {
      continue;
    }
    const duration = Number(raw.duration);
    clips[String(id)] = {
      id: String(id),
      label: String(raw.label || id),
      duration: Number.isFinite(duration) && duration > 0 ? duration : 1,
      loop: raw.loop !== false,
      update: raw.update
    };
  }
  return clips;
}

// Index meshData parts by label for m.get(). Labels are occurrence names in
// the instance tree; every part whose name matches (or whose id sits inside a
// matching group occurrence) belongs to the handle.
function partIdsByLabel(meshData) {
  const byLabel = new Map();
  for (const part of meshData?.parts || []) {
    const label = String(part.label || part.name || "").trim();
    if (!label) {
      continue;
    }
    if (!byLabel.has(label)) {
      byLabel.set(label, []);
    }
    byLabel.get(label).push(String(part.id));
  }
  return byLabel;
}

function partIdsForOccurrenceRefs(meshData, target) {
  const wanted = String(target).replace(/^#/, "").split(",").map((t) => t.trim()).filter(Boolean);
  if (!wanted.length || !wanted.every((t) => /^o[\d.]+$/.test(t))) {
    return null;
  }
  const ids = [];
  for (const part of meshData?.parts || []) {
    const id = String(part.id);
    if (wanted.some((t) => id === t || id.startsWith(`${t}.`))) {
      ids.push(id);
    }
  }
  return ids.length ? ids : null;
}

// One frame's evaluation surface. Collects per-part effects; the caller
// applies them to display records exactly like pose/step-module effects.
export function createAnimationFrame(THREE, meshData) {
  const byLabel = partIdsByLabel(meshData);
  const matrices = new Map(); // partId -> THREE.Matrix4
  const styles = new Map(); // partId -> {opacity?, visible?}

  const handleFor = (label) => {
    const partIds = byLabel.get(String(label).replace(/^#/, ""))
      || byLabel.get(String(label))
      || partIdsForOccurrenceRefs(meshData, label);
    if (!partIds || !partIds.length) {
      const known = [...byLabel.keys()].sort().join(", ") || "(none)";
      throw new Error(`animation: no occurrence labeled ${JSON.stringify(label)}; labels: ${known}`);
    }
    const applyMatrix = (matrix) => {
      for (const partId of partIds) {
        const current = matrices.get(partId);
        matrices.set(
          partId,
          current ? new THREE.Matrix4().multiplyMatrices(matrix, current) : matrix.clone()
        );
      }
    };
    const setStyle = (key, value) => {
      for (const partId of partIds) {
        const style = styles.get(partId) || {};
        style[key] = value;
        styles.set(partId, style);
      }
    };
    return {
      rotate(axis, degrees, origin = [0, 0, 0]) {
        const axisVec = new THREE.Vector3(axis[0], axis[1], axis[2]).normalize();
        const rotation = new THREE.Matrix4().makeRotationAxis(axisVec, (Number(degrees) || 0) * DEG_TO_RAD);
        const toOrigin = new THREE.Matrix4().makeTranslation(-origin[0], -origin[1], -origin[2]);
        const back = new THREE.Matrix4().makeTranslation(origin[0], origin[1], origin[2]);
        applyMatrix(new THREE.Matrix4().multiplyMatrices(back, new THREE.Matrix4().multiplyMatrices(rotation, toOrigin)));
        return this;
      },
      translate(vector) {
        applyMatrix(new THREE.Matrix4().makeTranslation(
          Number(vector[0]) || 0, Number(vector[1]) || 0, Number(vector[2]) || 0
        ));
        return this;
      },
      opacity(value) {
        setStyle("opacity", Math.max(0, Math.min(1, Number(value))));
        return this;
      },
      visible(value) {
        setStyle("visible", Boolean(value));
        return this;
      }
    };
  };

  const model = {
    get: handleFor,
    // Labels are enumerable so a clip can iterate without hardcoding.
    labels: () => [...byLabel.keys()].sort()
  };
  return { model, matrices, styles };
}

// Evaluate one clip at time t: a fresh frame each call (purity by
// construction). Returns {matrices, styles} keyed by part id.
export function evaluateAnimationClip(THREE, meshData, clip, t) {
  const frame = createAnimationFrame(THREE, meshData);
  const duration = clip.duration || 1;
  let localT = Math.max(0, Number(t) || 0);
  if (clip.loop !== false) {
    localT = localT % duration;
  } else {
    localT = Math.min(localT, duration);
  }
  clip.update(localT, frame.model);
  return { matrices: frame.matrices, styles: frame.styles };
}

// Merge an evaluated frame into the viewer's per-part effect records — the same
// records the kinematics module writes through ctx.effects, so animation
// COMPOSES OVER pose without either system knowing about the other. The
// animation matrix premultiplies whatever is already there (pose first, then
// choreography on top, in world space). Returns the number of parts whose
// transform the frame touched, which is what tells the caller its edge runtimes
// need re-deriving.
export function applyAnimationFrameToEffects(THREE, effectsByPartId, frame) {
  if (!effectsByPartId || !frame) {
    return 0;
  }
  const ensureEffect = (partId) => {
    const id = String(partId || "").trim();
    if (!id) {
      return null;
    }
    const current = effectsByPartId.get(id) || {
      matrix: null,
      style: null,
      visible: null,
      highlighted: false
    };
    effectsByPartId.set(id, current);
    return current;
  };
  let transformCount = 0;
  for (const [partId, matrix] of frame.matrices || []) {
    const effect = ensureEffect(partId);
    if (!effect) {
      continue;
    }
    effect.matrix = effect.matrix
      ? new THREE.Matrix4().multiplyMatrices(matrix, effect.matrix)
      : matrix.clone();
    transformCount += 1;
  }
  for (const [partId, style] of frame.styles || []) {
    const effect = ensureEffect(partId);
    if (!effect) {
      continue;
    }
    if (style && Object.hasOwn(style, "opacity")) {
      effect.style = { ...(effect.style || {}), opacity: style.opacity };
    }
    if (style && Object.hasOwn(style, "visible")) {
      effect.visible = style.visible !== false;
    }
  }
  return transformCount;
}
