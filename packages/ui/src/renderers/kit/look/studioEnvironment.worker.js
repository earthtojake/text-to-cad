import * as THREE from 'three';
import { createEnvironmentResource } from '@hardcore/core/common/environmentMap.js';

let renderer;
self.onmessage = async ({ data: { configuration, size } }) => {
  let resource;
  try {
    renderer ??= new THREE.WebGLRenderer({ canvas: new OffscreenCanvas(1, 1), antialias: false });
    resource = createEnvironmentResource(renderer, configuration, { size });
    const pixels = await resource.readPixels();
    self.postMessage(pixels, [pixels.data.buffer]);
  } catch (error) {
    self.postMessage({ error: String(error?.message || error) });
  } finally {
    resource?.dispose();
  }
};
