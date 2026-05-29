// Modal vibration playback for the dedicated modal GLB emitted by
// `cadpy_fea modal --modal-glb`. That GLB carries one morph target per mode and
// one baked glTF animation clip per mode (a sine-oscillated morph weight), with
// each clip named "mode <i> - <freq> Hz (<label>)" and per-mode metadata in the
// mesh extras. three.js GLTFLoader parses both natively, so this module just
// turns the loaded result into a mode list and drives an AnimationMixer.

const CLIP_NAME_RE =
  /^mode\s+(\d+)\s*-\s*([0-9]*\.?[0-9]+)\s*Hz(?:\s*\(([^)]*)\))?/i;

export function parseModalClipName(name) {
  const match = CLIP_NAME_RE.exec(String(name || "").trim());
  if (!match) return null;
  return {
    index: Number.parseInt(match[1], 10),
    frequencyHz: Number.parseFloat(match[2]),
    label: (match[3] || "").trim(),
  };
}

function meshExtrasModes(meshExtras) {
  const modes = meshExtras && Array.isArray(meshExtras.modes) ? meshExtras.modes : [];
  const byIndex = new Map();
  modes.forEach((m, i) => {
    const index = Number.isFinite(m?.index) ? Number(m.index) : i + 1;
    byIndex.set(index, m);
  });
  return byIndex;
}

// Build an ordered mode list from a loaded glTF-like result.
// Accepts { animations: [{name,...}], meshExtras: { modes: [...] } } so it is
// unit-testable without a full GLTFLoader; the real loader supplies the same
// fields (clip.name and mesh.userData for extras).
export function extractModalModes({ animations = [], meshExtras = null } = {}) {
  const extras = meshExtrasModes(meshExtras);
  const modes = animations.map((clip, i) => {
    const parsed = parseModalClipName(clip?.name) || {};
    const index = parsed.index ?? i + 1;
    const meta = extras.get(index) || {};
    const frequencyHz =
      Number.isFinite(meta.frequencyHz) ? Number(meta.frequencyHz) : parsed.frequencyHz ?? null;
    const label = meta.label || parsed.label || "";
    return {
      index,
      frequencyHz,
      label,
      clipName: clip?.name ?? `mode ${index}`,
      clipIndex: i,
    };
  });
  modes.sort((a, b) => a.index - b.index);
  return modes;
}

export function formatModeLabel(mode) {
  if (!mode) return "";
  const freq =
    mode.frequencyHz == null
      ? ""
      : `${Number(mode.frequencyHz).toFixed(Number(mode.frequencyHz) < 100 ? 2 : 1)} Hz`;
  const parts = [`Mode ${mode.index}`];
  if (freq) parts.push(freq);
  const head = parts.join(" — ");
  return mode.label ? `${head} (${mode.label})` : head;
}

export function findMorphMesh(root) {
  if (!root) return null;
  let found = null;
  root.traverse?.((obj) => {
    if (!found && obj.isMesh && Array.isArray(obj.morphTargetInfluences) && obj.morphTargetInfluences.length) {
      found = obj;
    }
  });
  return found;
}

// Drives modal playback: select a mode, play/pause, set speed and a live
// amplitude multiplier (the baked clip animates to weight 1; amplitude scales
// the visible deflection without re-baking).
export class ModalPlayer {
  constructor({ THREE, root, animations, meshExtras = null }) {
    if (!THREE) throw new Error("ModalPlayer requires a THREE namespace.");
    this.THREE = THREE;
    this.root = root;
    this.animations = animations || [];
    this.modes = extractModalModes({ animations: this.animations, meshExtras });
    this.mesh = findMorphMesh(root);
    this.mixer = new THREE.AnimationMixer(root);
    this.action = null;
    this.activeIndex = this.modes.length ? this.modes[0].index : null;
    this.amplitude = 1;
    this.playing = false;
    if (this.activeIndex != null) this.selectMode(this.activeIndex);
  }

  selectMode(index) {
    const mode = this.modes.find((m) => m.index === index) || this.modes[0];
    if (!mode) return null;
    const wasPlaying = this.playing;
    if (this.action) this.action.stop();
    const clip = this.animations[mode.clipIndex];
    this.action = clip ? this.mixer.clipAction(clip) : null;
    if (this.action) {
      this.action.reset();
      this.action.setLoop(this.THREE.LoopRepeat, Infinity);
      this.action.play();
      this.action.paused = !wasPlaying;
    }
    this.activeIndex = mode.index;
    this.playing = wasPlaying;
    return mode;
  }

  play() {
    this.playing = true;
    if (this.action) this.action.paused = false;
  }

  pause() {
    this.playing = false;
    if (this.action) this.action.paused = true;
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
    return this.playing;
  }

  setSpeed(speed) {
    this.mixer.timeScale = Math.max(0, Number(speed) || 0);
  }

  setAmplitude(amplitude) {
    this.amplitude = Math.max(0, Number(amplitude) || 0);
  }

  // Advance the animation by dtSeconds and apply the amplitude multiplier.
  update(dtSeconds) {
    this.mixer.update(Math.max(0, Number(dtSeconds) || 0));
    if (this.mesh && this.amplitude !== 1) {
      const inf = this.mesh.morphTargetInfluences;
      for (let i = 0; i < inf.length; i += 1) inf[i] *= this.amplitude;
    }
    return this.mesh ? this.mesh.morphTargetInfluences : null;
  }

  activeMode() {
    return this.modes.find((m) => m.index === this.activeIndex) || null;
  }

  dispose() {
    this.mixer.stopAllAction();
    if (this.mixer.uncacheRoot && this.root) this.mixer.uncacheRoot(this.root);
    this.action = null;
  }
}
