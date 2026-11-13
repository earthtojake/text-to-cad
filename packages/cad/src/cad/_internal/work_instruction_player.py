"""A picture guide you can turn in your hands: its steps as a GLB and a page that plays it.

The GLB is the assembly with one animation, ``assemble``: each step's parts appear at their
turn and travel in along the step's arrow, so the clip run backward takes it apart. It is made
the way a model makes one (``cad.build123d.animation``), on the instruction's own copy of the assembly
handed over as its own document, so the model is untouched and any GLB viewer plays the file.

The page holds that GLB, the steps and the PDF's picture of each part, and needs no server: open
it in a browser, turn the model, and go through the steps with Next and Back. It is drawn as the
PDF is: line art (white faces, inked creases, a heavier outline round each part) on a camera with
no perspective, the step's parts blue, its number big and its parts box over the model's corner. Only three.js comes from the network, at the
version the viewer uses. If it cannot, the page says so.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from cad._internal.work_instruction_guide import NOTICES, _chip_text, _kind, hardware, plain, says
from cad._internal.work_instruction_pages import FILL, GUIDE_LINE, _extent, _group, parts
from cad.work_instruction import ARROWS

CLIP = "assemble"
TURN = 1.8  # seconds a step has in the clip
TRAVEL = 1.2  # of which its parts are moving
REACH = 0.35  # how far they start from their place, of the assembly's diagonal
HOLD = 0.8  # seconds the page shows a step's parts pulled apart before they go in
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
    from cad.build123d import animation

    show = animation(wi.shape, CLIP, duration=len(wi.steps) * TURN)
    for ref, path, keys, interpolation in channels(wi):
        show.channel(ref, path=path, keys=keys, interpolation=interpolation)
    cad.model.export(cad.model(wi.shape, name=re.sub(r"\W+", "_", f"{wi.source_name}_guide")), target)


def _hardware(lines) -> list[dict[str, str]]:
    return [{"kind": _kind(line.name), "text": _chip_text(line)} for line in lines]


def steps(wi) -> list[dict[str, Any]]:
    """What the page says at each step, as the guide's pages say it: its parts box (each part's
    picture and count, its screws by size, the tools it uses), then its notes and lines."""
    index_of = {ref: index for index, (_name, refs, _steps) in enumerate(parts(wi)) for ref in refs}
    return [{"label": step.label, "title": step.title,
             "parts": [{"count": len(refs), "name": plain(name), "picture": f"part-{index_of[refs[0]]}"}
                       for name, refs in _group(step.units)],
             "hardware": _hardware(hardware([step])),
             "tools": list(dict.fromkeys(op.tool for op in step.ops if op.tool)),
             "notices": [{"careful": notice.caption != "NOTE", "text": f"{NOTICES[notice.caption]}: {notice.value}"}
                         for notice in step.notices],
             "says": [{"kind": kind, "text": text} for kind, text in says(step, surfaces=False, need=False)]}
            for step in wi.steps]


def need(wi) -> dict[str, Any]:
    """What you need, as the PDF's first page lists it: each part, the screws by size, the tools."""
    screws = hardware(wi.steps)
    return {"parts": [{"count": len(refs), "name": plain(name), "picture": f"part-{index}"}
                      for index, (name, refs, _steps) in enumerate(parts(wi))],
            "hardware": _hardware(screws),
            "tools": [{"name": tool, "use": " and ".join(line.name for line in screws if tool in line.tools)}
                      for tool in wi.equipment()]}


def page(wi, glb: bytes, pictures: dict | None = None) -> str:
    """The page, whole: its steps, the PDF's picture of each part, and its GLB inside it."""
    shown = {str(name): "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
             for name, path in (pictures or {}).items() if str(name).startswith("part-")}
    data = {"title": wi.title, "scope": wi.scope.value if wi.scope else "", "turn": TURN, "travel": TRAVEL, "hold": HOLD,
            "clip": CLIP, "steps": steps(wi), "need": need(wi), "pictures": shown}
    return (_PAGE.replace("__THREE__", THREE).replace("__FILL__", FILL).replace("__LINE__", GUIDE_LINE)
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
  --paper: #ffffff; --ink: #111111; --soft: #555555; --faint: #d9d9d9; --wash: #f4f4f4; --open: #9a5b00;
  --sans: Verdana, "DejaVu Sans", Geneva, sans-serif;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { display: grid; grid-template-columns: minmax(0, 1fr) 380px; background: var(--paper); color: var(--ink);
  font: 15px/1.45 var(--sans); }
#stage { position: relative; min-height: 0; touch-action: none; }
canvas { display: block; width: 100%; height: 100%; outline: none; }
#hint { position: absolute; right: 24px; bottom: 20px; color: var(--soft); font-size: 13px; pointer-events: none; }
#card { position: absolute; left: 24px; top: 20px; max-width: min(360px, calc(100% - 48px)); pointer-events: none; }
#num { font-size: 88px; font-weight: 700; line-height: 0.9; letter-spacing: -0.03em; }
#num:empty { display: none; }
.box { margin-top: 10px; padding: 10px 12px; border: 1.5px solid var(--ink); border-radius: 10px; background: var(--paper); }
.box:empty { display: none; }
.box h2 { margin: 0 0 8px; font-size: 14px; font-weight: 700; }
.tiles { display: flex; flex-wrap: wrap; gap: 6px 12px; }
.tile { width: 72px; }
.tile img { display: block; width: 72px; height: 72px; object-fit: contain; }
.tile b { display: block; font-size: 13px; }
.tile span { display: block; color: var(--soft); font-size: 11px; line-height: 1.25; }
.wide .tile { width: 96px; } .wide .tile img { width: 96px; height: 96px; }
.row { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 13px; font-weight: 700; }
.row svg { flex: none; width: 30px; height: 16px; }
.row small { color: var(--soft); font-weight: 400; }
aside { display: flex; flex-direction: column; min-height: 0; border-left: 1.5px solid var(--ink); }
header { padding: 26px 24px 16px; }
h1 { margin: 0; font-size: 30px; font-weight: 700; line-height: 1.1; text-transform: uppercase; letter-spacing: 0.01em; }
header p { margin: 8px 0 0; color: var(--soft); }
ol { flex: 1; margin: 0; padding: 0; overflow-y: auto; list-style: none; border-top: 1.5px solid var(--ink); }
li { border-bottom: 1px solid var(--faint); }
li > button { display: grid; grid-template-columns: 40px 1fr 20px; align-items: center; gap: 4px; width: 100%;
  padding: 12px 24px; border: 0; background: none; color: var(--soft); font: inherit; text-align: left; cursor: pointer; }
li > button b { font-size: 22px; font-weight: 700; line-height: 1; }
li > button i { width: 18px; height: 18px; border: 1.5px solid var(--faint); border-radius: 3px; }
li.done > button { color: var(--ink); }
li.done > button i { border-color: var(--ink); background: var(--ink)
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='white' stroke-width='2'/%3E%3C/svg%3E") center/14px no-repeat; }
li.now { background: var(--wash); }
li.now > button { color: var(--ink); }
li.now > button i { border-color: var(--ink); }
.more { padding: 0 24px 14px 68px; font-size: 14px; }
.more p { margin: 4px 0; }
.more .small { color: var(--soft); font-size: 12px; }
.more .open { color: var(--open); }
.notice { display: flex; gap: 10px; align-items: center; margin: 4px 0 8px; padding: 8px 10px;
  border: 1.5px solid var(--ink); border-radius: 10px; }
.notice svg { flex: none; width: 24px; height: 24px; }
footer { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; padding: 16px 24px; border-top: 1.5px solid var(--ink); }
footer button { height: 44px; border: 1.5px solid var(--ink); border-radius: 10px; background: var(--paper); color: var(--ink);
  font: 700 15px var(--sans); cursor: pointer; }
footer button:disabled { border-color: var(--faint); color: var(--faint); cursor: default; }
footer #next { background: var(--ink); color: var(--paper); }
footer #next:disabled { border-color: var(--faint); background: var(--paper); color: var(--faint); }
button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
#modes { position: absolute; left: 24px; bottom: 14px; display: flex; gap: 4px; padding: 4px;
  border: 1.5px solid var(--ink); border-radius: 10px; background: var(--paper); }
#modes button { display: flex; align-items: center; gap: 6px; height: 32px; padding: 0 9px; border: 0; border-radius: 7px;
  background: none; color: var(--ink); font: 12px var(--sans); cursor: pointer; }
#modes button svg { width: 18px; height: 18px; flex: none; }
#modes button[aria-checked="true"] { background: var(--ink); color: var(--paper); }
#fail { position: absolute; inset: 0; display: none; place-items: center; padding: 24px; color: var(--soft); text-align: center; }
@media (max-width: 760px) {
  body { grid-template-columns: minmax(0, 1fr); grid-template-rows: 52vh minmax(0, 1fr); }
  aside { border-left: 0; border-top: 1.5px solid var(--ink); }
  header { padding: 14px 16px 10px; } h1 { font-size: 22px; }
  #card { left: 12px; top: 10px; display: flex; align-items: flex-start; gap: 10px; max-width: calc(100% - 24px);
    max-height: calc(100% - 36px); overflow: hidden; }
  #num { font-size: 48px; }
  .box { margin-top: 0; padding: 6px 8px; border-radius: 8px; } .box h2 { font-size: 12px; margin-bottom: 4px; }
  .tiles { gap: 4px 8px; } .tile, .wide .tile { width: 40px; } .tile img, .wide .tile img { width: 40px; height: 40px; }
  .tile b { font-size: 11px; } .tile span { display: none; }
  .row { margin-top: 3px; gap: 6px; font-size: 11px; } .row svg { width: 24px; height: 13px; } .row small { display: none; }
  li > button { padding: 12px 16px; } .more { padding: 0 16px 12px 60px; } footer { padding: 12px 16px; }
  #hint { display: none; }
  #modes { left: 12px; bottom: 8px; } #modes button { padding: 0 7px; } #modes button span { display: none; }
}
</style>
<script type="importmap">
{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@__THREE__/build/three.module.min.js",
             "three/addons/": "https://cdn.jsdelivr.net/npm/three@__THREE__/examples/jsm/"}}
</script>
</head>
<body>
<main id="stage"><div id="card"><div id="num"></div><div id="box" class="box"></div></div>
  <div id="modes" role="radiogroup" aria-label="Display"></div>
  <div id="hint">Drag to turn it.</div><div id="fail"></div></main>
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
// A millisecond in: the GLB keeps its times as 32-bit floats, and 5.4 so kept is a little after 5.4.
const start = (index) => index * data.turn + 1e-3;
const landed = (index) => start(index) + data.travel;

// Small drawings, the PDF's: screws, nuts and washers side on, the tools by what their names say.
const SVG = (body, box = "0 0 30 16") =>
  `<svg viewBox="${box}" fill="white" stroke="#111" stroke-width="1.2" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const GLYPHS = {
  screw: SVG('<rect x="1" y="3" width="6" height="10"/><rect x="7" y="5.5" width="21" height="5"/>' +
             '<path d="M10 5.5l1.6 5M13 5.5l1.6 5M16 5.5l1.6 5M19 5.5l1.6 5M22 5.5l1.6 5M25 5.5l1.6 5" stroke-width="0.8"/>'),
  nut: SVG('<path d="M15 1.5l6 3.5v6l-6 3.5-6-3.5v-6z"/><circle cx="15" cy="8" r="2.6"/>'),
  washer: SVG('<circle cx="15" cy="8" r="6.5"/><circle cx="15" cy="8" r="2.8"/>'),
};
function toolGlyph(name) {
  const lowered = name.toLowerCase();
  if (/hex|allen/.test(lowered)) return SVG('<path d="M9 2v11h12" fill="none" stroke-width="3" stroke-linecap="round"/>');
  if (/screwdriver/.test(lowered)) return SVG('<rect x="2" y="5" width="11" height="6" rx="2"/><path d="M13 8h15" stroke-width="2"/>');
  if (/wrench|spanner/.test(lowered)) return SVG('<path d="M3 13L19 5" stroke-width="3" stroke-linecap="round"/><circle cx="22" cy="4" r="3.5"/>');
  return SVG('<circle cx="15" cy="8" r="3" fill="#111"/>');
}
const SIGNS = {
  careful: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5L22.5 21h-21z" fill="white" stroke="#111" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9v6" stroke="#111" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="18" r="1.3" fill="#111"/></svg>',
  tip: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="white" stroke="#111" stroke-width="1.8"/><path d="M12 11v6" stroke="#111" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="7.5" r="1.3" fill="#111"/></svg>',
};

function el(tag, className, text) {
  const made = document.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined) made.textContent = text;
  return made;
}

// A parts box, as the PDF draws one: each part's picture and count, its screws by size, the tools.
function partsBox(box, what, heading, named) {
  box.replaceChildren();
  box.classList.toggle("wide", named);
  if (heading) box.append(el("h2", "", heading));
  if (what.parts.length) {
    const tiles = el("div", "tiles");
    for (const part of what.parts) {
      const tile = el("div", "tile");
      tile.title = part.name;
      const picture = data.pictures[part.picture];
      if (picture) { const img = el("img"); img.src = picture; img.alt = part.name; tile.append(img); }
      tile.append(el("b", "", `${part.count}x`));
      if (named || !picture) tile.append(el("span", "", part.name));
      tiles.append(tile);
    }
    box.append(tiles);
  }
  for (const line of what.hardware) {
    const row = el("div", "row");
    row.innerHTML = GLYPHS[line.kind];
    row.append(el("span", "", line.text));
    box.append(row);
  }
  for (const tool of what.tools) {
    const row = el("div", "row");
    const name = typeof tool === "string" ? tool : tool.name;
    row.innerHTML = toolGlyph(name);
    row.append(el("span", "", name));
    if (tool.use) row.append(el("small", "", `for ${tool.use}`));
    box.append(row);
  }
}

function say(parent, kind, text) {
  parent.append(el("p", kind, text));
}

const rows = data.steps.map((step, index) => {
  const row = el("li");
  const button = el("button");
  button.append(el("b", "", step.label), el("span", "", step.title), el("i"));
  button.addEventListener("click", () => show(index));
  const more = el("div", "more");
  more.hidden = true;
  for (const notice of step.notices) {
    const line = el("div", "notice");
    line.innerHTML = notice.careful ? SIGNS.careful : SIGNS.tip;
    line.append(el("span", "", notice.text));
    more.append(line);
  }
  for (const line of step.says) say(more, line.kind, line.text);
  row.append(button, more);
  $("steps").append(row);
  return row;
});

let now = -1, time = 0, moving = null, playing = false, seek = () => {}, glow = () => {}, paint = () => {};

// The CAD Viewer's display modes, by its names, words and icons: the same sphere drawn as each
// mode draws a model. Hidden line is the PDF's line art, and the page opens on it.
const SPHERE = (body) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const SHADE = '<path d="M12 3a9 9 0 0 1 0 18a1.35 9 0 0 0 0-18Z" fill="currentColor" fill-opacity="0.45" stroke="none"/>';
const EQUATOR = "M3 12a9 3.5 0 0 0 18 0";
const MODES = [
  { value: "solid", label: "Solid", title: "Shaded surfaces with visible CAD edges",
    icon: SPHERE(`${SHADE}<circle cx="12" cy="12" r="9"/><path d="${EQUATOR}"/>`) },
  { value: "shaded", label: "Shaded", title: "Shaded surfaces, no edges",
    icon: SPHERE(`<circle cx="12" cy="12" r="9" fill="currentColor" fill-opacity="0.12" stroke-opacity="0.45"/>${SHADE}`) },
  { value: "parts", label: "Parts", title: "Each part its own colour, with visible CAD edges",
    icon: SPHERE('<path d="M3 12a9 9 0 0 1 18 0a9 3.5 0 0 1-18 0Z" fill="currentColor" fill-opacity="0.5" stroke="none"/>' +
      '<path d="M3 12a9 3.5 0 0 0 18 0a9 9 0 0 1-18 0Z" fill="currentColor" fill-opacity="0.15" stroke="none"/>' +
      `<circle cx="12" cy="12" r="9"/><path d="${EQUATOR}"/>`) },
  { value: "xray", label: "X-ray", title: "Transparent surfaces with visible and hidden CAD edges",
    icon: SPHERE(`<circle cx="12" cy="12" r="9" fill="currentColor" fill-opacity="0.12"/><path d="${EQUATOR}"/>` +
      '<path d="M3 12a9 3.5 0 0 1 18 0" stroke-dasharray="1.5 2" stroke-opacity="0.55"/>') },
  { value: "hidden-line", label: "Hidden line", title: "Visible contours with obscured edges removed",
    icon: SPHERE(`<circle cx="12" cy="12" r="9"/><path d="${EQUATOR}M12 3a3.5 9 0 0 0 0 18"/>`) },
  { value: "wireframe", label: "Wireframe", title: "All CAD edges through the model",
    icon: SPHERE(`<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a3.5 9 0 0 0 0 18M12 3a3.5 9 0 0 1 0 18${EQUATOR}"/>`) },
];
let mode = "hidden-line";
try { const kept = localStorage.getItem("work-instruction-display"); if (MODES.some((m) => m.value === kept)) mode = kept; } catch {}
const modeButtons = MODES.map((option) => {
  const button = el("button");
  button.setAttribute("role", "radio");
  button.title = option.title;
  button.setAttribute("aria-label", option.label);
  button.innerHTML = option.icon;
  button.append(el("span", "", option.label));
  button.addEventListener("click", () => {
    mode = option.value;
    try { localStorage.setItem("work-instruction-display", mode); } catch {}
    showMode();
  });
  $("modes").append(button);
  return button;
});
function showMode() {
  MODES.forEach((option, index) => modeButtons[index].setAttribute("aria-checked", String(option.value === mode)));
  paint();
}
showMode();

function mark() {
  rows.forEach((row, index) => {
    row.classList.toggle("now", index === now);
    row.classList.toggle("done", index < now);
    row.lastChild.hidden = index !== now;
    if (index === now) row.scrollIntoView({ block: "nearest" });
  });
  $("num").textContent = now < 0 ? "" : data.steps[now].label;
  if (now < 0) partsBox($("box"), data.need, "What you need", true);
  else partsBox($("box"), data.steps[now], "", false);
  $("back").disabled = now < 0;
  $("next").disabled = now >= last;
  $("next").textContent = now < 0 ? "Start" : "Next";
  $("play").textContent = playing ? "Pause" : "Play all";
  glow(now);
}

// Runs the clip from one time to another, backward as well, and calls then when it gets there;
// first holding where it starts for wait seconds.
function run(from, to, rate, then, wait = 0) {
  moving = null;
  if (calm) { seek(to); time = to; if (then) then(); return; }
  time = from;
  seek(from);
  moving = { to, rate: Math.sign(to - from) * rate, then, wait };
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
  // A step's parts wait pulled apart, as the PDF draws them, then go in.
  if (index === was + 1 || (index === was && index >= 0)) run(start(index), landed(index), 1, then, data.hold);
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

// The outline drawn round each part: its back faces pushed out a few pixels on the screen, in ink.
const HULL_VERTEX = `
uniform float thickness;
uniform vec2 resolution;
void main() {
  vec4 clip = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  vec2 way = (projectionMatrix * vec4(normalize(normalMatrix * normal), 0.0)).xy;
  float length2 = dot(way, way);
  if (length2 > 1e-8) clip.xy += way * inversesqrt(length2) * thickness * clip.w * 2.0 / resolution;
  gl_Position = clip;
}`;
const HULL_FRAGMENT = `void main() { gl_FragColor = vec4(0.067, 0.067, 0.067, 1.0); }`;

try {
  const THREE = await import("three");
  const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const { LineSegments2 } = await import("three/addons/lines/LineSegments2.js");
  const { LineSegmentsGeometry } = await import("three/addons/lines/LineSegmentsGeometry.js");
  const { LineMaterial } = await import("three/addons/lines/LineMaterial.js");
  const { RoomEnvironment } = await import("three/addons/environments/RoomEnvironment.js");

  const stage = $("stage");
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0xffffff, 1);
  stage.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  // One camera with no perspective, as the PDF's pictures are drawn.
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const bytes = Uint8Array.from(atob($("model").textContent.trim()), (c) => c.charCodeAt(0));
  const gltf = await new Promise((done, failed) => new GLTFLoader().parse(bytes.buffer, "", done, failed));
  scene.add(gltf.scene);

  const clip = gltf.animations.find((found) => found.name === data.clip);
  const mixer = new THREE.AnimationMixer(gltf.scene);
  const action = mixer.clipAction(clip);
  action.play();
  action.paused = true;
  const end = data.steps.length * data.turn;
  seek = (at) => { action.time = Math.min(at, clip.duration - 1e-3); time = at; mixer.update(0); };
  seek(end);

  const box = new THREE.Box3().setFromObject(gltf.scene);
  const middle = box.getCenter(new THREE.Vector3());
  const radius = box.getBoundingSphere(new THREE.Sphere()).radius;
  controls.target.copy(middle);
  camera.position.copy(middle).add(new THREE.Vector3(1, 0.85, 1.2).normalize().multiplyScalar(radius * 4));
  camera.near = 0;
  camera.far = radius * 8;

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
  // A first step's part that does not move is in no track: it is whatever no track reaches.
  gltf.scene.traverse((mesh) => {
    if (!mesh.isMesh) return;
    for (let up = mesh; up; up = up.parent) if (timed.has(up)) return;
    added[0].push(mesh);
  });

  // A thin line from where each part starts to where it lands, from its leading face, as the PDF draws it.
  const lineInk = new LineMaterial({ color: new THREE.Color("__LINE__"), linewidth: 2 });
  const headInk = new THREE.MeshBasicMaterial({ color: new THREE.Color("__LINE__") });
  const guides = added.map((parts, index) => {
    const group = new THREE.Group();
    for (const part of parts) {
      seek(start(index));
      const pulled = new THREE.Box3().setFromObject(part);
      seek(landed(index));
      const placed = new THREE.Box3().setFromObject(part);
      if (pulled.isEmpty() || placed.isEmpty()) continue;
      const from = pulled.getCenter(new THREE.Vector3());
      const to = placed.getCenter(new THREE.Vector3());
      const way = to.clone().sub(from);
      if (way.length() < radius * 1e-3) continue;
      way.normalize();
      const size = placed.getSize(new THREE.Vector3());
      const lead = way.clone().multiplyScalar(
        0.5 * (Math.abs(way.x) * size.x + Math.abs(way.y) * size.y + Math.abs(way.z) * size.z));
      from.add(lead);
      to.add(lead);
      const line = new LineSegments2(new LineSegmentsGeometry().setPositions([...from.toArray(), ...to.toArray()]), lineInk);
      const head = new THREE.Mesh(new THREE.ConeGeometry(radius * 0.018, radius * 0.06, 16), headInk);
      head.position.copy(to).addScaledVector(way, -radius * 0.03);
      head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), way);
      group.add(line, head);
    }
    group.visible = false;
    scene.add(group);
    return group;
  });
  seek(end);

  // Each mesh carries every look a mode needs: white paper (Hidden line), its own colour shaded
  // (Solid, Shaded, Parts), glass (X-ray); its creases inked, and the outline round it a little
  // heavier. A mode picks which show; X-ray and Wireframe draw the creases through the model.
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.9;
  const creaseInk = new LineMaterial({ color: 0x111111, linewidth: 1.5 });
  const creaseNew = new LineMaterial({ color: new THREE.Color("__FILL__"), linewidth: 1.5 });
  const hullInk = new THREE.ShaderMaterial({
    uniforms: { thickness: { value: 1.6 }, resolution: { value: new THREE.Vector2(1, 1) } },
    vertexShader: HULL_VERTEX, fragmentShader: HULL_FRAGMENT, side: THREE.BackSide,
  });
  // Parts' own colours: none blue (blue is what a step adds), none red, amber or green.
  const PARTS = ["#c9b8e8", "#9fd3cc", "#ecb8cf", "#e3d3b4", "#b9a0c9", "#cfc9c0"].map((hex) => new THREE.Color(hex));
  const owner = new Map();  // mesh -> { step, index }: the step that adds its part, and the part's place
  let count = 0;
  added.forEach((parts, step) => parts.forEach((part) => {
    const index = count++;
    part.traverse((mesh) => { if (mesh.isMesh && !owner.has(mesh)) owner.set(mesh, { step, index }); });
  }));
  const meshes = [];
  gltf.scene.traverse((mesh) => { if (mesh.isMesh) meshes.push(mesh); });
  const looks = new Map();
  const behind = { polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 };
  for (const mesh of meshes) {
    if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals();
    const own = mesh.material.color ? mesh.material.color.clone() : new THREE.Color(0xc8c8c8);
    const creases = new LineSegments2(
      new LineSegmentsGeometry().fromEdgesGeometry(new THREE.EdgesGeometry(mesh.geometry, 30)), creaseInk);
    const hull = new THREE.Mesh(mesh.geometry, hullInk);
    mesh.add(creases, hull);
    looks.set(mesh, { own, creases, hull,
      paper: new THREE.MeshBasicMaterial({ color: 0xffffff, ...behind }),
      shade: new THREE.MeshStandardMaterial({ color: own, roughness: 0.6, metalness: 0, ...behind }),
      glass: new THREE.MeshBasicMaterial({ color: own, transparent: true, opacity: 0.18, depthWrite: false }) });
  }

  // The model is framed in the room the step's card leaves it: below the card or beside it,
  // whichever is bigger, so the card never covers it.
  const size = () => {
    const width = stage.clientWidth, height = Math.max(stage.clientHeight, 1);
    renderer.setSize(width, height, false);
    const card = $("card").getBoundingClientRect(), there = stage.getBoundingClientRect();
    const right = card.right - there.left + 8, below = card.bottom - there.top + 8, foot = 28;
    const rooms = [[0, below, width, height - foot], [right, 0, width, height - foot]]
      .map(([x0, y0, x1, y1]) => ({ x0, y0, x1, y1, fits: Math.min(x1 - x0, y1 - y0) }));
    const room = rooms[0].fits >= rooms[1].fits ? rooms[0] : rooms[1];
    const scale = Math.max(room.fits, 40) / (radius * 2.2);  // pixels to a model unit
    const x = (room.x0 + room.x1) / 2, y = (room.y0 + room.y1) / 2;
    Object.assign(camera, { left: -x / scale, right: (width - x) / scale, top: y / scale, bottom: -(height - y) / scale });
    camera.updateProjectionMatrix();
    const pixels = renderer.getDrawingBufferSize(new THREE.Vector2());
    for (const ink of [creaseInk, creaseNew, lineInk]) ink.resolution.set(width, height);
    hullInk.uniforms.resolution.value.copy(pixels);
    hullInk.uniforms.thickness.value = 1.6 * renderer.getPixelRatio();
  };
  size();
  const watch = new ResizeObserver(size);
  watch.observe(stage);
  watch.observe($("card"));

  const blue = new THREE.Color("__FILL__");  // what a step adds, as the PDF's pictures show it, in every mode
  const white = new THREE.Color(0xffffff);
  paint = () => {
    const through = mode === "xray" || mode === "wireframe";
    creaseInk.depthTest = creaseNew.depthTest = !through;
    for (const [mesh, look] of looks) {
      const mine = owner.get(mesh);
      const fresh = mine !== undefined && mine.step === now;
      if (mode === "hidden-line") {
        mesh.material = look.paper;
        look.paper.color.copy(fresh ? blue : white);
      } else if (mode === "xray" || mode === "wireframe") {
        mesh.material = look.glass;
        look.glass.color.copy(fresh ? blue : look.own);
        look.glass.opacity = fresh ? 0.4 : 0.18;
      } else {
        mesh.material = look.shade;
        look.shade.color.copy(fresh ? blue : mode === "parts" ? PARTS[(mine?.index ?? 0) % PARTS.length] : look.own);
      }
      mesh.material.visible = mode !== "wireframe";
      look.creases.visible = mode !== "shaded";
      look.creases.material = fresh && through ? creaseNew : creaseInk;
      look.hull.visible = mode === "hidden-line" || mode === "solid" || mode === "parts";
    }
  };
  glow = (index) => {
    paint();
    guides.forEach((group, at) => { group.visible = at === index; });
  };

  mark();
  let then = performance.now();
  renderer.setAnimationLoop((clock) => {
    const dt = Math.min((clock - then) / 1000, 0.05);
    then = clock;
    if (moving && moving.wait > 0) moving.wait -= dt;
    else if (moving) {
      const next = time + moving.rate * dt;
      const there = moving.rate > 0 ? next >= moving.to : next <= moving.to;
      seek(there ? moving.to : next);
      if (there) { const done = moving.then; moving = null; if (done) done(); }
    }
    if (now >= 0) guides[now].visible = time < landed(now) - 1e-3;  // the line goes once its parts are in
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
