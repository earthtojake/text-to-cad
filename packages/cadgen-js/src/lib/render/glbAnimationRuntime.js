export function createGlbAnimationRuntime(THREE, scene, clip) {
  if (!THREE || !scene || !clip) return null;
  const mixer = new THREE.AnimationMixer(scene);
  const action = mixer.clipAction(clip);
  action.setLoop(THREE.LoopOnce, 1);
  action.clampWhenFinished = true;
  action.play();
  return { mixer, action, scene };
}

export function setGlbAnimationTime(runtime, elapsedSec) {
  if (!runtime) return;
  // LoopOnce clamps by pausing at its endpoint. An absolute scrub or replay
  // must reactivate the action before setTime or Three leaves the pose at zero.
  runtime.action.enabled = true;
  runtime.action.paused = false;
  runtime.mixer.setTime(Math.max(Number(elapsedSec) || 0, 0));
}

export function disposeGlbAnimationRuntime(runtime) {
  if (!runtime) return;
  runtime.action.stop();
  runtime.mixer.stopAllAction();
  runtime.mixer.uncacheRoot(runtime.scene);
}
