// A disabled view can still carry an interrupted collapse. Only a settled
// rest pose is a no-op when a new mesh publication reruns the effect.
export function inactiveExplodedViewNeedsReset(animation, records) {
  return Number(animation?.progress) !== 0
    || (Array.isArray(records) && records.some(record => record?.explodedViewMatrix != null));
}
