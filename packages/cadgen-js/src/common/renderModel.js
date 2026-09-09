import {
  fitCameraToModel
} from "./cadScene.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function addLight(scene, light, enabled = true) {
  light.visible = enabled;
  scene.add(light);
  return light;
}

function applyViewportLighting(THREE, scene, theme = {}) {
  const lighting = theme.lighting || {};
  addLight(
    scene,
    new THREE.HemisphereLight(
      lighting.hemisphere?.skyColor || "#ffffff",
      lighting.hemisphere?.groundColor || "#101014",
      toFiniteNumber(lighting.hemisphere?.intensity, 0)
    ),
    lighting.hemisphere?.enabled === true
  );
  addLight(
    scene,
    new THREE.AmbientLight(
      lighting.ambient?.color || "#ffffff",
      toFiniteNumber(lighting.ambient?.intensity, 0.2)
    ),
    lighting.ambient?.enabled !== false
  );
  const directionalLights = Array.isArray(lighting.directionalLights)
    ? lighting.directionalLights
    : [lighting.directional || {}];
  for (const config of directionalLights) {
    const light = new THREE.DirectionalLight(
      config.color || "#ffffff",
      toFiniteNumber(config.intensity, 1)
    );
    const position = config.position || {};
    light.position.set(
      toFiniteNumber(position.x, 160),
      toFiniteNumber(position.y, -140),
      toFiniteNumber(position.z, 240)
    );
    light.castShadow = config.castShadow === true;
    addLight(scene, light, config.enabled !== false);
  }
}

function resolveViewportSize(hostElement, canvas, fallbackWidth = 1400, fallbackHeight = 900) {
  const rect = hostElement?.getBoundingClientRect?.();
  const width = Math.max(1, Math.floor(rect?.width || hostElement?.clientWidth || canvas?.clientWidth || fallbackWidth));
  const height = Math.max(1, Math.floor(rect?.height || hostElement?.clientHeight || canvas?.clientHeight || fallbackHeight));
  return { width, height };
}

function applyBackground(THREE, renderer, scene, theme = {}, { alpha = false } = {}) {
  const background = theme.background || {};
  if (alpha || background.type === "transparent") {
    scene.background = null;
    renderer.setClearColor(new THREE.Color("#000000"), 0);
    return;
  }
  const color = background.solidColor || background.color || "#ffffff";
  scene.background = new THREE.Color(color);
  renderer.setClearColor(new THREE.Color(color), 1);
}

export function renderModel(THREE, model, options = {}) {
  if (!THREE) {
    throw new Error("renderModel requires THREE");
  }
  if (!model?.root) {
    throw new Error("renderModel requires a model returned by buildModel");
  }
  const canvas = options.canvas || undefined;
  const hostElement = options.hostElement || options.container || canvas?.parentElement || null;
  const theme = options.theme || options.themeSettings || {};
  const alpha = options.alpha === true;
  const renderer = options.renderer || new THREE.WebGLRenderer({
    canvas,
    alpha,
    antialias: options.antialias !== false,
    powerPreference: options.powerPreference || "high-performance",
    preserveDrawingBuffer: options.preserveDrawingBuffer === true,
    logarithmicDepthBuffer: options.logarithmicDepthBuffer !== false
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = options.shadows !== false;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = options.scene || new THREE.Scene();
  applyBackground(THREE, renderer, scene, theme, { alpha });
  applyViewportLighting(THREE, scene, theme);
  scene.add(model.root);

  const camera = options.camera || new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 10000);
  const frame = {
    direction: options.direction || options.view?.direction || [1, -1, 0.8],
    up: options.up || options.view?.up || [0, 0, 1],
    padding: toFiniteNumber(options.padding, 0.12),
    scale: options.scale || options.sceneScale || "cad",
    lockedHalfHeightScale: options.lockedHalfHeightScale || null
  };
  let disposed = false;
  let rafId = 0;
  let lastRenderTime = typeof performance !== "undefined" ? performance.now() : 0;

  const resize = () => {
    const { width, height } = resolveViewportSize(hostElement, renderer.domElement, options.width, options.height);
    renderer.setPixelRatio(clamp(toFiniteNumber(options.pixelRatio, globalThis.devicePixelRatio || 1), 1, options.maxPixelRatio || 2));
    renderer.setSize(width, height, false);
    model.runtime?.syncScreenSpaceLineMaterials?.(width, height);
    const fit = fitCameraToModel(THREE, camera, model.bounds, {
      direction: frame.direction,
      up: frame.up,
      width,
      height,
      padding: frame.padding,
      scale: frame.scale
    });
    if (frame.lockedHalfHeightScale) {
      fitCameraToModel(THREE, camera, model.bounds, {
        direction: frame.direction,
        lockedHalfHeight: fit.halfHeight * toFiniteNumber(frame.lockedHalfHeightScale, 1),
        up: frame.up,
        width,
        height,
        padding: frame.padding,
        scale: frame.scale
      });
    }
    return { width, height, fit };
  };

  const render = () => {
    renderer.render(scene, camera);
  };

  const step = () => {
    if (disposed) {
      return;
    }
    const now = typeof performance !== "undefined" ? performance.now() : lastRenderTime;
    const deltaSeconds = Math.min(Math.max((now - lastRenderTime) / 1000, 0), 0.1);
    lastRenderTime = now;
    options.beforeRender?.({ deltaSeconds, viewport: api });
    render();
    rafId = globalThis.requestAnimationFrame?.(step) || 0;
  };

  const start = () => {
    if (!rafId) {
      lastRenderTime = typeof performance !== "undefined" ? performance.now() : 0;
      rafId = globalThis.requestAnimationFrame?.(step) || 0;
    }
  };

  const stop = () => {
    if (rafId) {
      globalThis.cancelAnimationFrame?.(rafId);
      rafId = 0;
    }
  };

  const resizeObserver = options.autoResize === false || typeof ResizeObserver !== "function" || !hostElement
    ? null
    : new ResizeObserver(() => {
        resize();
        if (options.autoRender === false) {
          render();
        }
      });
  resizeObserver?.observe(hostElement);

  const api = {
    THREE,
    model,
    renderer,
    scene,
    camera,
    ready: Promise.resolve(),
    resize,
    render,
    start,
    stop,
    capturePng() {
      render();
      return renderer.domElement.toDataURL("image/png");
    },
    dispose() {
      if (disposed) {
        return;
      }
      disposed = true;
      stop();
      resizeObserver?.disconnect();
      scene.remove(model.root);
      if (options.disposeModel !== false) {
        model.dispose?.();
      }
      if (!options.renderer) {
        renderer.dispose();
      }
    }
  };

  resize();
  if (options.autoStart === true) {
    start();
  } else if (options.autoRender !== false) {
    render();
  }
  return api;
}
