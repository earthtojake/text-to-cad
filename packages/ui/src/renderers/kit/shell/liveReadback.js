// Whether the camera on screen is the one a command asked for, as the live binding and the
// shell's own `setCamera` predicate read it. A plain module so the tests import the real
// comparison rather than a copy of it.

// The camera reads back what was asked when position and target agree to a part in ten thousand
// of their size (a float32 round trip through the viewport's matrices is well inside that).
export const near = (actual, asked) =>
  actual.length === asked.length && asked.every((value, index) => Math.abs((actual[index] ?? Number.NaN) - value) <= 1e-4 * Math.max(1, Math.abs(value)));

/** The camera on screen reads back as `asked` in position and target. */
export const cameraReadsBack = (camera, asked) =>
  Boolean(camera) && near(camera.position, asked.position) && near(camera.target, asked.target);

/**
 * The same, while Preview's orbit is playing: every frame turns the camera about its up axis, so
 * the applied camera is on screen when the target, the distance and the height along up agree and
 * the azimuth is free. (The orbit never stops for a drag, so no frame reads back exactly.)
 */
export const orbitReadsBack = (camera, asked) => {
  if (!camera || !near(camera.target, asked.target)) return false;
  const up = asked.up;
  const upLength = Math.hypot(...up) || 1;
  const offset = position => position.map((value, index) => value - asked.target[index]);
  const height = position => offset(position).reduce((sum, value, index) => sum + value * up[index] / upLength, 0);
  return near([Math.hypot(...offset(camera.position))], [Math.hypot(...offset(asked.position))])
    && near([height(camera.position)], [height(asked.position)]);
};
