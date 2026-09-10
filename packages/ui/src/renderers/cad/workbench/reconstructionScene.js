import * as THREE from 'three';
import { assemblyPlaybackFrames } from './reconstructionAssembly.js';

/** Shared renderer for live playback and exports; owns all of its GPU resources. */
export function createReconstructionScene(data) {
  const scene = new THREE.Scene(), renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  const camera = new THREE.PerspectiveCamera(36, 1, .01, 1e8);
  camera.up.set(0, 0, 1);
  const group = new THREE.Group(); scene.add(group);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x556677, 2.5));
  const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(2, -3, 5); scene.add(light);
  const box = new THREE.Box3(new THREE.Vector3(...data.bounds.slice(0, 3)), new THREE.Vector3(...data.bounds.slice(3)));
  const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3()).length() || 1;
  const render = () => renderer.render(scene, camera);
  const resize = (width, height) => {
    renderer.setSize(width, height); camera.aspect = width / height;
    camera.position.copy(center).add(new THREE.Vector3(1, -1.4, 1).normalize().multiplyScalar(size * 1.8 / Math.min(camera.aspect, 1)));
    camera.near = Math.max(size / 10000, .00001); camera.far = size * 100;
    camera.lookAt(center); camera.updateProjectionMatrix();
  };
  const clear = () => {
    const geometries = new Set(), materials = new Set();
    group.traverse(child => { if (child.geometry) geometries.add(child.geometry); if (child.material) materials.add(child.material); });
    group.clear(); geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose());
  };
  const show = (frame, original = false) => {
    clear();
    if (data.tracks) {
      const geometries = new Map();
      for (const { occurrence, mesh, lines, active, context } of assemblyPlaybackFrames(data, frame, original)) {
        const instance = new THREE.Group();
        // STEP occurrence matrices are row-major; Three stores column-major.
        instance.matrix.fromArray(occurrence.transform).transpose(); instance.matrixAutoUpdate = false;
        if (mesh?.vertices.length) {
          let geometry = geometries.get(mesh);
          if (!geometry) {
            geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.Float32BufferAttribute(mesh.vertices, 3));
            geometry.setAttribute('normal', new THREE.Float32BufferAttribute(mesh.normals, 3));
            if (mesh.indices) geometry.setIndex(ArrayBuffer.isView(mesh.indices) ? new THREE.BufferAttribute(mesh.indices, 1) : mesh.indices);
            geometries.set(mesh, geometry);
          }
          const color = occurrence.color ? new THREE.Color().fromArray(occurrence.color) : new THREE.Color(0xa8b9c6);
          instance.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, roughness: .6, metalness: .12,
            side: THREE.DoubleSide, emissive: active ? 0x163249 : 0, emissiveIntensity: .3,
            transparent: context, opacity: context ? .18 : 1, depthWrite: !context })));
        }
        for (const line of lines) {
          const geometry = new THREE.BufferGeometry().setFromPoints(line.map(p => new THREE.Vector3(...p)));
          instance.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x73b7ff, depthTest: false })));
        }
        group.add(instance);
      }
      render(); return;
    }
    const step = data.steps[frame], solid = step.solidFrame;
    const mesh = original ? data.reference : solid == null ? { vertices: [], normals: [] } : data.steps[solid];
    if (mesh.vertices.length) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(mesh.vertices, 3));
      geometry.setAttribute('normal', new THREE.Float32BufferAttribute(mesh.normals, 3));
      if (mesh.indices) geometry.setIndex(mesh.indices);
      group.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xa8b9c6, roughness: .6, metalness: .12, side: THREE.DoubleSide })));
    }
    if (!original) for (const line of step.lines) {
      const geometry = new THREE.BufferGeometry().setFromPoints(line.map(p => new THREE.Vector3(...p)));
      group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x73b7ff, depthTest: false })));
    }
    render();
  };
  return { renderer, camera, center, resize, render, show, dispose() { clear(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove(); } };
}
