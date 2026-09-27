export const CAD_DEFAULT_VERTICAL_FOV_DEGREES = 48;

export function explicitViewerFocalLength(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : null;
}

export function perspectiveDistanceScale(previousFovDegrees, nextFovDegrees) {
  const previous = Number(previousFovDegrees) * Math.PI / 180;
  const next = Number(nextFovDegrees) * Math.PI / 180;
  const scale = Math.tan(previous / 2) / Math.tan(next / 2);
  return Number.isFinite(scale) && scale > 0 ? scale : 1;
}
