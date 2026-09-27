// Release a scene object and everything under it: geometry (unless a shared cache
// owns it), materials and their maps, and its place in the graph.
export function disposeSceneObject(object) {
  if (!object) {
    return;
  }
  while (object.children?.length) {
    disposeSceneObject(object.children[0]);
  }
  if (typeof object.userData?.beforeDispose === "function") {
    object.userData.beforeDispose(object);
    delete object.userData.beforeDispose;
  }
  if (object.geometry?.userData?.cadSceneCachedGeometry !== true) {
    object.geometry?.dispose?.();
  }
  const materials = Array.isArray(object.material) ? object.material : [object.material];
  for (const material of materials) {
    material?.map?.dispose?.();
    material?.alphaMap?.dispose?.();
    material?.dispose?.();
  }
  object.parent?.remove(object);
}
