// Bake Jake's PR #374 icon into a decorative loading image. No 3D renderer
// runs alongside the CAD viewport. Regeneration needs desktop npm dependencies
// and the WebP CLI tools; normal builds use the checked-in images.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(path.join(root, "apps/desktop/package.json"));
const { build } = require("esbuild");
const { chromium } = require("playwright");
const sourceCommit = "ed6a16b25936031adfa0a6d4705d80e1c712eb37";
const sourcePath = "apps/docs/src/lib/icon/model.mjs";
const out = path.join(root, "apps/web/src/client/assets/brand");
await fs.mkdir(path.join(root, "tmp"), { recursive: true });
const scratch = await fs.mkdtemp(path.join(root, "tmp/loading-icon-"));
const size = 192;
const frames = 400;
const frameMs = 50;

let source;
try {
  source = execFileSync("git", ["show", `${sourceCommit}:${sourcePath}`], { cwd: root, encoding: "utf8" });
} catch {
  throw new Error("Fetch the icon source first: git fetch upstream pull/374/head");
}
await fs.writeFile(path.join(scratch, "model.mjs"), source);
const bundle = await build({
  stdin: {
    resolveDir: scratch,
    contents: `
      import * as THREE from 'three';
      import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
      import { createIcon, expansionAt, ORBIT_SECONDS } from './model.mjs';
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      renderer.setSize(${size}, ${size});
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.05;
      document.body.append(renderer.domElement);
      const scene = new THREE.Scene();
      const room = new RoomEnvironment();
      const pmrem = new THREE.PMREMGenerator(renderer);
      const environment = pmrem.fromScene(room, 0.04);
      scene.environment = environment.texture;
      scene.environmentIntensity = 0.15;
      room.dispose(); pmrem.dispose();
      scene.add(new THREE.HemisphereLight('#ffffff', '#202020', 0.15));
      for (const [intensity, position] of [[4.5, [-5,6,2]], [0.15, [4,0,2]], [2.5, [1,3,-5]]]) {
        const light = new THREE.DirectionalLight('#ffffff', intensity);
        light.position.set(...position); scene.add(light);
      }
      const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
      camera.position.set(0,0,10); camera.lookAt(0,0,0);
      const { group, prongs } = createIcon();
      group.traverse(object => {
        if (!object.isMesh) return;
        object.material.color.set('#b8bbc0');
        object.material.metalness = 0.35;
        object.material.roughness = 0.35;
      });
      scene.add(group);
      const reference = group.quaternion.clone();
      const up = new THREE.Vector3(0,1,0);
      window.frameAt = seconds => {
        // The playground defaults to 4x: 2-second contractions, 20-second orbit.
        const time = seconds * 4;
        for (const prong of prongs) prong.morphTargetInfluences[0] = expansionAt(time);
        group.quaternion.setFromAxisAngle(up, 2*Math.PI*time/ORBIT_SECONDS).multiply(reference);
        renderer.render(scene,camera);
        return renderer.domElement.toDataURL('image/png').split(',')[1];
      };
    `,
  },
  nodePaths: [path.join(root, "apps/desktop/node_modules")],
  bundle: true,
  write: false,
  format: "iife",
});

const browser = await chromium.launch({ headless: true, args: ["--use-angle=metal"] });
try {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent("<!doctype html><body style='margin:0'></body>");
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const files = [];
  for (let i = 0; i < frames; i++) {
    const png = await page.evaluate(seconds => window.frameAt(seconds), i * frameMs / 1000);
    const file = path.join(scratch, `${String(i).padStart(4, "0")}.png`);
    await fs.writeFile(file, Buffer.from(png, "base64"));
    files.push(file);
  }
  await fs.mkdir(out, { recursive: true });
  execFileSync("img2webp", ["-loop", "0", "-lossy", "-q", "85", "-d", String(frameMs), ...files, "-o", path.join(out, "hardcore-loading.webp")]);
  execFileSync("cwebp", ["-quiet", "-lossless", files[0], "-o", path.join(out, "hardcore-still.webp")]);
  console.log(`Rendered ${frames} frames, ${frames * frameMs / 1000}s loop -> ${path.relative(root, out)}`);
} finally {
  await browser.close();
  await fs.rm(scratch, { recursive: true, force: true });
}
