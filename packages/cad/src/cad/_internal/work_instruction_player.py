"""A picture guide you can turn in your hands: its steps as a GLB and a page that plays it.

The GLB is the assembly with one animation, ``assemble``: each step's parts appear at their
turn and travel in along the step's arrow, so the clip run backward takes it apart. It is made
the way a model makes one (``cad.gltf.animation``), on the instruction's own copy of the assembly
handed over as its own document, so the model is untouched and any GLB viewer plays the file.

The page holds that GLB and the steps, and needs no server: open it in a browser, turn the
model, and go through the steps with Next and Back. Only three.js comes from the network, at the
version the viewer uses. If it cannot, the page says so.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from cad._internal.work_instruction_guide import NOTICES, says
from cad._internal.work_instruction_pages import FILL, _extent
from cad.work_instruction import ARROWS

CLIP = "assemble"
TURN = 1.8  # seconds a step has in the clip
TRAVEL = 1.2  # of which its parts are moving
REACH = 0.35  # how far they start from their place, of the assembly's diagonal
THREE = "0.187.0"  # the viewer's (packages/ui)


def channels(wi) -> list[tuple[str, str, list, str]]:
    """The clip as ``(part ref, path, keys, interpolation)``: every part hidden until its step,
    then travelling in along the step's arrow. Offsets are held from the clip's start, so
    each part's way in is one curve; a step's move is eased at both ends."""
    _centre, diagonal = _extent(wi)
    found = []
    for index, step in enumerate(wi.steps):
        start = index * TURN
        for ref in step.install:
            if index:
                found.append((ref, "scale", [(0.0, 0.0), (start, 1.0)], "STEP"))
            if step.arrow:
                offset = tuple(round(-way * REACH * diagonal, 4) for way in ARROWS[step.arrow])
                keys = [(0.0, offset), (start, offset)] if index else [(0.0, offset)]
                found.append((ref, "translation", [*keys, (start + TRAVEL, (0.0, 0.0, 0.0))], "CUBICSPLINE"))
    return found


def write_glb(wi, target: Path) -> None:
    """The assembly with its ``assemble`` clip, at ``target``."""
    import cad
    from cad.gltf import animation

    show = animation(wi.shape, CLIP, duration=len(wi.steps) * TURN)
    for ref, path, keys, interpolation in channels(wi):
        show.channel(ref, path=path, keys=keys, interpolation=interpolation)
    cad.export(cad.model(wi.shape, name=re.sub(r"\W+", "_", f"{wi.source_name}_guide")), target)


def steps(wi) -> list[dict[str, Any]]:
    """What the page says at each step, as the guide's pages say it."""
    return [{"label": step.label, "title": step.title,
             "notices": [{"careful": notice.caption != "NOTE", "text": f"{NOTICES[notice.caption]}: {notice.value}"}
                         for notice in step.notices],
             "says": [{"kind": kind, "text": text} for kind, text in says(step, surfaces=False)]} for step in wi.steps]


def page(wi, glb: bytes) -> str:
    """The page, whole: its steps and its GLB inside it."""
    data = {"title": wi.title, "scope": wi.scope.value if wi.scope else "", "turn": TURN, "travel": TRAVEL,
            "clip": CLIP, "steps": steps(wi)}
    return (_PAGE.replace("__THREE__", THREE).replace("__FILL__", FILL)
            .replace("__TITLE__", _escaped(wi.title))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__GLB__", base64.b64encode(glb).decode("ascii")))


def _escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --paper: #f7f3ee; --ink: #1b1a18; --soft: #6b665e; --rule: #ddd6cb; --accent: #1f5fd6; --careful: #9a5b00;
  --sans: "Inter Tight", "Helvetica Neue", Arial, sans-serif;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { display: grid; grid-template-columns: minmax(0, 1fr) 380px; background: var(--paper); color: var(--ink);
  font: 16px/1.4 var(--sans); }
#stage { position: relative; min-height: 0; touch-action: none; }
canvas { display: block; width: 100%; height: 100%; outline: none; }
#hint { position: absolute; left: 24px; bottom: 20px; color: var(--soft); font-size: 14px; pointer-events: none; }
aside { display: flex; flex-direction: column; min-height: 0; border-left: 1px solid var(--rule); }
header { padding: 28px 24px 16px; }
h1 { margin: 0; font-size: 28px; line-height: 1.15; letter-spacing: -0.01em; }
header p { margin: 8px 0 0; color: var(--soft); }
ol { flex: 1; margin: 0; padding: 0; overflow-y: auto; list-style: none; border-top: 1px solid var(--rule); }
li { border-bottom: 1px solid var(--rule); }
li > button { display: grid; grid-template-columns: 32px 1fr; width: 100%; padding: 12px 24px; border: 0; background: none;
  color: var(--soft); font: inherit; text-align: left; cursor: pointer; }
li > button b { font-weight: 600; }
li.done > button { color: var(--ink); }
li.now > button { color: var(--ink); font-weight: 600; }
li.now > button b { color: var(--accent); }
.more { padding: 0 24px 14px 56px; font-size: 15px; }
.more p { margin: 4px 0; }
.more .need, .more .small { color: var(--soft); }
.more .small { font-size: 13px; }
.more .careful, .more .open { color: var(--careful); }
footer { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; padding: 16px 24px; border-top: 1px solid var(--rule); }
footer button { height: 44px; border: 1px solid var(--ink); border-radius: 8px; background: none; color: var(--ink);
  font: 600 16px var(--sans); cursor: pointer; }
footer button:disabled { border-color: var(--rule); color: var(--rule); cursor: default; }
footer #next { border-color: var(--accent); background: var(--accent); color: #fff; }
footer #next:disabled { border-color: var(--rule); background: none; color: var(--rule); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
#fail { position: absolute; inset: 0; display: none; place-items: center; padding: 24px; color: var(--soft); text-align: center; }
@media (max-width: 760px) {
  body { grid-template-columns: minmax(0, 1fr); grid-template-rows: 48vh minmax(0, 1fr); }
  aside { border-left: 0; border-top: 1px solid var(--rule); }
  header { padding: 16px 16px 12px; } h1 { font-size: 22px; }
  li > button { padding: 12px 16px; } .more { padding: 0 16px 12px 48px; } footer { padding: 12px 16px; }
  #hint { left: 16px; bottom: 10px; }
}
</style>
<script type="importmap">
{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@__THREE__/build/three.module.min.js",
             "three/addons/": "https://cdn.jsdelivr.net/npm/three@__THREE__/examples/jsm/"}}
</script>
</head>
<body>
<main id="stage"><div id="hint">Drag to turn it.</div><div id="fail"></div></main>
<aside>
  <header><h1 id="title"></h1><p id="scope"></p></header>
  <ol id="steps"></ol>
  <footer><button id="back">Back</button><button id="play">Play all</button><button id="next">Start</button></footer>
</aside>
<script type="application/json" id="guide">__DATA__</script>
<script type="text/plain" id="model">__GLB__</script>
<script type="module">
const data = JSON.parse(document.getElementById("guide").textContent);
const $ = (id) => document.getElementById(id);
$("title").textContent = data.title;
$("scope").textContent = data.scope;
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
const last = data.steps.length - 1;
const start = (index) => index * data.turn;
const landed = (index) => start(index) + data.travel;

function say(parent, kind, text) {
  const line = document.createElement("p");
  line.className = kind;
  line.textContent = text;
  parent.append(line);
}

const rows = data.steps.map((step, index) => {
  const row = document.createElement("li");
  const button = document.createElement("button");
  const number = document.createElement("b");
  const words = document.createElement("span");
  number.textContent = step.label;
  words.textContent = step.title;
  button.append(number, words);
  button.addEventListener("click", () => show(index));
  const more = document.createElement("div");
  more.className = "more";
  more.hidden = true;
  for (const notice of step.notices) say(more, notice.careful ? "careful" : "", notice.text);
  for (const line of step.says) say(more, line.kind, line.text);
  row.append(button, more);
  $("steps").append(row);
  return row;
});

let now = -1, time = 0, moving = null, playing = false, seek = () => {}, glow = () => {};

function mark() {
  rows.forEach((row, index) => {
    row.classList.toggle("now", index === now);
    row.classList.toggle("done", index < now);
    row.lastChild.hidden = index !== now;
    if (index === now) row.scrollIntoView({ block: "nearest" });
  });
  $("back").disabled = now < 0;
  $("next").disabled = now >= last;
  $("next").textContent = now < 0 ? "Start" : "Next";
  $("play").textContent = playing ? "Pause" : "Play all";
  glow(now);
}

// Runs the clip from one time to another, backward as well, and calls then when it gets there.
function run(from, to, rate, then) {
  moving = null;
  if (calm) { seek(to); time = to; if (then) then(); return; }
  time = from;
  seek(from);
  moving = { to, rate: Math.sign(to - from) * rate, then };
}

function show(index) {
  playing = false;
  go(index);
}

function go(index, then) {
  const was = now;
  now = index;
  mark();
  const rest = () => { seek(index < 0 ? data.steps.length * data.turn : landed(index)); glow(now); if (then) then(); };
  if (index === was + 1 || (index === was && index >= 0)) run(start(index), landed(index), 1, then);
  else if (index === was - 1) run(landed(was), start(was), 1.6, rest);  // its parts leave as they came
  else rest();
}

function playOn() {
  if (!playing) return;
  if (now >= last) { playing = false; mark(); return; }
  go(now + 1, () => setTimeout(playOn, calm ? 1500 : 700));
}

$("next").addEventListener("click", () => show(now + 1));
$("back").addEventListener("click", () => show(now - 1));
$("play").addEventListener("click", () => {
  playing = !playing;
  if (playing && now >= last) { now = -1; }
  mark();
  playOn();
});
addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight" && now < last) show(now + 1);
  if (event.key === "ArrowLeft" && now >= 0) show(now - 1);
});
mark();

try {
  const THREE = await import("three");
  const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const { RoomEnvironment } = await import("three/addons/environments/RoomEnvironment.js");

  const stage = $("stage");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  stage.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.5;
  const camera = new THREE.PerspectiveCamera(28, 1, 0.001, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const bytes = Uint8Array.from(atob($("model").textContent.trim()), (c) => c.charCodeAt(0));
  const gltf = await new Promise((done, failed) => new GLTFLoader().parse(bytes.buffer, "", done, failed));
  scene.add(gltf.scene);

  const box = new THREE.Box3().setFromObject(gltf.scene);
  const middle = box.getCenter(new THREE.Vector3());
  const radius = box.getBoundingSphere(new THREE.Sphere()).radius;
  camera.near = radius / 100;
  camera.far = radius * 40;
  controls.target.copy(middle);
  const place = () => {
    const distance = radius * 1.08 / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(camera.aspect, 1);
    camera.position.copy(middle).add(new THREE.Vector3(1, 0.85, 1.2).normalize().multiplyScalar(distance));
    camera.updateProjectionMatrix();
  };
  const size = () => {
    renderer.setSize(stage.clientWidth, stage.clientHeight, false);
    camera.aspect = stage.clientWidth / Math.max(stage.clientHeight, 1);
    camera.updateProjectionMatrix();
  };
  size();
  place();
  new ResizeObserver(size).observe(stage);

  const clip = gltf.animations.find((found) => found.name === data.clip);
  const mixer = new THREE.AnimationMixer(gltf.scene);
  const action = mixer.clipAction(clip);
  action.play();
  action.paused = true;
  const end = data.steps.length * data.turn;
  seek = (at) => { action.time = Math.min(at, clip.duration - 1e-3); time = at; mixer.update(0); };

  // Which parts each step adds, read off the clip: the first time each part's scale is not zero.
  const added = data.steps.map(() => []);
  const timed = new Set();
  for (const track of clip.tracks) {
    if (!track.name.endsWith(".scale")) continue;
    const part = gltf.scene.getObjectByName(track.name.slice(0, -6));
    if (!part) continue;
    timed.add(part);
    const key = Array.from({ length: track.times.length }, (_, at) => at).find((at) => track.values[at * 3] > 0.5);
    added[Math.round(track.times[key ?? 0] / data.turn)]?.push(part);
  }
  for (const track of clip.tracks) {
    const part = gltf.scene.getObjectByName(track.name.split(".")[0]);
    if (part && !timed.has(part)) { timed.add(part); added[0].push(part); }
  }
  const blue = new THREE.Color("__FILL__");  // what a step adds, as the PDF's pictures show it
  const lit = (part, on) => part.traverse((mesh) => {
    if (!mesh.isMesh) return;
    if (!mesh.userData.own) { mesh.material = mesh.material.clone(); mesh.userData.own = mesh.material.color.clone(); }
    mesh.material.color.copy(on ? blue : mesh.userData.own);
  });
  glow = (index) => added.forEach((parts, at) => parts.forEach((part) => lit(part, at === index)));

  seek(end);
  mark();
  let then = performance.now();
  renderer.setAnimationLoop((clock) => {
    const dt = Math.min((clock - then) / 1000, 0.05);
    then = clock;
    if (moving) {
      const next = time + moving.rate * dt;
      const there = moving.rate > 0 ? next >= moving.to : next <= moving.to;
      seek(there ? moving.to : next);
      if (there) { const done = moving.then; moving = null; if (done) done(); }
    }
    controls.update();
    renderer.render(scene, camera);
  });
  renderer.domElement.addEventListener("pointerdown", () => { $("hint").hidden = true; }, { once: true });
} catch (error) {
  console.error(error);
  $("hint").hidden = true;
  $("fail").style.display = "grid";
  $("fail").textContent = "The 3D view could not start. It needs an internet connection to load its viewer, and a browser with WebGL.";
}
</script>
</body>
</html>
"""
