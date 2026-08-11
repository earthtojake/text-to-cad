export const DEFAULT_ORBIT_FPS = 6;
export const DEFAULT_ORBIT_DURATION_SECONDS = 12;

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function orbitFrameOutputs(job) {
  const orbit = isObject(job.orbit) ? job.orbit : {};
  const output = Array.isArray(job.outputs) && job.outputs.length && isObject(job.outputs[0])
    ? job.outputs[0]
    : {};
  const width = Math.max(1, Math.floor(Number(output.width || job.width || orbit.width || 720)));
  const height = Math.max(1, Math.floor(Number(output.height || job.height || orbit.height || 480)));
  const fps = Math.max(1, Math.min(Number(orbit.fps || DEFAULT_ORBIT_FPS), 60));
  const durationSeconds = Math.max(0.1, Math.min(Number(orbit.durationSeconds || DEFAULT_ORBIT_DURATION_SECONDS), 60));
  const frameCount = Math.max(2, Math.min(Math.round(fps * durationSeconds), 720));
  const startAzimuth = Number.isFinite(Number(orbit.startAzimuth)) ? Number(orbit.startAzimuth) : -45;
  const elevation = Number.isFinite(Number(orbit.elevation)) ? Number(orbit.elevation) : 28;
  const turns = Number.isFinite(Number(orbit.turns)) ? Number(orbit.turns) : 1;
  return {
    path: String(output.path || job.output || ""),
    width,
    height,
    fps,
    durationSeconds,
    frameCount,
    theme: output.theme || job.theme || "workbench",
    graphics: {
      ...(isObject(job.graphics) ? job.graphics : {}),
      ...(isObject(output.graphics) ? output.graphics : {}),
    },
    render: {
      ...(isObject(job.render) ? job.render : {}),
      ...(isObject(output.render) ? output.render : {}),
    },
    outputs: Array.from({ length: frameCount }, (_, index) => ({
      path: "",
      width,
      height,
      camera: `${startAzimuth + ((360 * turns * index) / frameCount)}:${elevation}`,
    }))
  };
}
