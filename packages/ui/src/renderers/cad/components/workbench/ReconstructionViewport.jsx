import { useEffect, useRef } from 'react';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createReconstructionScene } from '../../workbench/reconstructionScene.js';

/** Disposable preview scene; never mutates the document viewer or its selections. */
export default function ReconstructionViewport({ data, frame, original, viewRef }) {
  const container = useRef(null), runtime = useRef(null);
  useEffect(() => {
    const host = container.current, view = createReconstructionScene(data);
    view.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
    host.appendChild(view.renderer.domElement);
    const controls = new OrbitControls(view.camera, view.renderer.domElement);
    controls.addEventListener('change', view.render);
    const resize = new ResizeObserver(() => {
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) return;
      view.resize(width, height); controls.target.copy(view.center); controls.update(); view.render();
    });
    resize.observe(host); runtime.current = view;
    if (viewRef) viewRef.current = view;
    return () => { resize.disconnect(); controls.dispose(); view.dispose(); runtime.current = null; if (viewRef) viewRef.current = null; };
  }, [data, viewRef]);
  useEffect(() => { runtime.current?.show(frame, original); }, [data, frame, original]);
  return <div ref={container} className="h-full min-h-48 w-full touch-none" aria-label={original ? 'Original STEP solid' : `Reconstruction: ${data.steps[frame].label}`} />;
}
