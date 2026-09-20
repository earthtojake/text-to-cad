// Keeps the last framebuffer visible while the existing scene is reconciled.
// Compilation uses Three's public async API; no renderer/context replacement.
export function createViewUpdateGate(runtime) {
  let held = false, disposed = false;
  const frames = new Set();
  return {
    get held() { return held; },
    hold() { held = true; },
    async compile() {
      if (!disposed) await runtime.renderer.compileAsync(runtime.scene, runtime.camera);
    },
    present() {
      if (disposed) return Promise.reject(new Error('Viewer closed'));
      held = false;
      return new Promise((resolve, reject) => {
        frames.add({ resolve, reject });
        runtime.requestRender();
      });
    },
    didDraw() {
      for (const frame of frames) frame.resolve();
      frames.clear();
    },
    dispose() {
      disposed = true;
      for (const frame of frames) frame.reject(new Error('Viewer closed'));
      frames.clear();
    },
  };
}
