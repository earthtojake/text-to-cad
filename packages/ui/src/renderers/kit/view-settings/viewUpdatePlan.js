// Resource boundaries, never preset names. Uniform/transform changes reuse the
// live scene; structural changes prepare before their first visible frame.
export function viewPreparationKey(scene) {
  const v = scene.view;
  return JSON.stringify([
    scene.appearance, v.surfaces.style, v.surfaces.colorMode, v.surfaces.opacity < 0.999,
    v.edges.enabled, v.edges.visibility,
    v.lighting.enabled, v.lighting.enabled && [v.lighting.quality, v.lighting.size, v.lighting.fill],
    v.floor.enabled, v.clip.enabled,
  ]);
}

export function viewUpdateLabel(previous, next) {
  if (!previous?.view.clip.enabled && next.view.clip.enabled) return 'Preparing section view…';
  return 'Updating view…';
}

export function afterViewPaint() {
  // A microtask or a single rAF still runs before paint. Yield a browser task
  // after rAF so controls can paint before any synchronous scene reconciliation.
  // The timer is the floor where no frame comes (a hidden tab). Whichever comes
  // first settles it and the other finds it settled: nothing is cancelled, so a
  // late timer never reaches for a frame API its page no longer has.
  return new Promise(resolve => {
    setTimeout(resolve, 100);
    requestAnimationFrame(() => setTimeout(resolve, 0));
  });
}
