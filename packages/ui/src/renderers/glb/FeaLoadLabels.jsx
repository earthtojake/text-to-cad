import { useEffect, useRef } from "react";
import { besideEnd, chromeCovers, clearAlong, colourBarCover, roomAlong, settleLabels } from "./feaChrome.js";
import { GHOST_OPACITY, pastOutline } from "./feaMarkers.js";

// The panels' 11px, in the viewer's own face.
const FONT_SIZE = "500 11px";
// Past the arrows' free ends, away from the face, clear of the shafts.
const OFFSET_PX = 10;
// A label's line, for keeping labels off each other: the 11px text and its halo.
const LINE_PX = 14;
// Whether the model hides a label, and where along its arrow it lies clear of the part, is cast at most this often
// while the view moves, and once more when it stops: about a dozen rays through the result mesh per label (the slide's
// halving one at a time), not per frame.
const HIDDEN_EVERY_MS = 100;
// Where the chrome over the view is (the strip and the panels, `chromeCovers`; the colour bar, `colourBarCover`) is read from
// the page at most this often.
const COVER_EVERY_MS = 250;

/**
 * Each load's amount ("300 N", "2 MPa") beside its arrows, drawn over the view on a canvas that
 * takes no pointer. `labels()` hands the current ones (`createFeaMarkers().labels`, in the result
 * mesh's space, following the deformation drawn); a frame loop repaints them, so they follow the
 * camera. A label behind the camera is left out. A label stands outside the model's outline on screen
 * (`pastOutline`, from its box's `corners`), carried on along its marker's line; one whose marker stands on
 * its face sits at its own arrow's outer end instead (`besideEnd`, its text running on the way the arrow
 * points) wherever that end is in sight, slid on along the arrow's line just past the part where the end's own
 * spot lies over it (`clearAlong`), so it stays by its arrow and no label is ever drawn inside or behind the part. No label is drawn past the view's edge, under the tool strip and its
 * panels at the view's left or the colour bar at its foot, nor over another label (`settleLabels`), on every
 * frame, however the view has turned. `colours`: the ink and the halo it sits on. A label the model hides
 * all the same (a ray from the eye meets the part before it) is drawn as its arrows are there, a faint ghost.
 */
export default function FeaLoadLabels({ runtimeRef, hostRef, mesh, labels, colours }) {
  const canvasRef = useRef(null);
  const live = useRef({ mesh, labels, colours });
  live.current = { mesh, labels, colours };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let frameId = 0;
    let painted = "";
    let castFor = "";
    let castAt = 0;
    let hidden = [];
    let raycaster = null;
    let covers = [];
    let coverAt = -Infinity;
    let measure = null;
    let endClear = [];
    const paint = () => {
      frameId = window.requestAnimationFrame(paint);
      const runtime = runtimeRef.current;
      const host = hostRef.current;
      if (!runtime?.camera || !host) return;
      const { mesh: shownMesh, labels: read, colours: tones } = live.current;
      const width = host.clientWidth || 1;
      const height = host.clientHeight || 1;
      const dpr = window.devicePixelRatio || 1;
      runtime.camera.updateMatrixWorld();
      shownMesh.updateWorldMatrix(true, false);
      const point = new runtime.THREE.Vector3();
      const screen = (at) => {
        point.fromArray(at).applyMatrix4(shownMesh.matrixWorld);
        if (point.clone().applyMatrix4(runtime.camera.matrixWorldInverse).z >= -runtime.camera.near) return null;
        point.project(runtime.camera);
        return [((point.x + 1) * width) / 2, ((1 - point.y) * height) / 2];
      };
      const ndc = new runtime.THREE.Vector2();
      const target = new runtime.THREE.Vector3();
      // Whether the model lies between the eye and `at` (in the mesh's space), along the ray through `through`
      // (a label drawn on screen) or straight at it.
      const blocked = (caster, at, through, straight) => {
        target.fromArray(at).applyMatrix4(shownMesh.matrixWorld);
        if (straight) {
          const eye = runtime.camera.getWorldPosition(new runtime.THREE.Vector3());
          caster.set(eye, target.clone().sub(eye).normalize());
        } else caster.setFromCamera(ndc.set((through.x / width) * 2 - 1, 1 - (through.y / height) * 2), runtime.camera);
        caster.far = caster.ray.origin.distanceTo(target) * 0.99;
        return caster.intersectObject(shownMesh, false).length > 0;
      };
      // Whether a label drawn here lies over the model on screen: a ray through its end nearer its arrow meets the part
      // at all (`whole`: or through its middle or its far end).
      const overModel = (caster, label, whole = true) => {
        const toward = label.align === "right" ? -1 : label.align === "center" ? 0 : 1;
        caster.far = Infinity;
        return (whole ? [0, 0.5, 1] : [0]).map((share) => label.x + toward * share * label.width).some((x) => {
          caster.setFromCamera(ndc.set((x / width) * 2 - 1, 1 - (label.y / height) * 2), runtime.camera);
          return caster.intersectObject(shownMesh, false).length > 0;
        });
      };
      const now = window.performance.now();
      if (now - coverAt >= COVER_EVERY_MS) {
        covers = [...chromeCovers(host), colourBarCover(host)];
        coverAt = now;
      }
      if (!measure) {
        const context = canvas.getContext("2d");
        if (context) context.font = `${FONT_SIZE} ${window.getComputedStyle(host).fontFamily || "sans-serif"}`;
        measure = (text) => context?.measureText(text).width || text.length * 6;
      }
      // Each label's two places: outside the model's outline, carried on along its marker's line (`pastOutline`),
      // and, for a marker standing on its face, at its own arrow's outer end (`besideEnd`).
      const candidates = [];
      for (const label of read()) {
        const free = screen(label.at);
        if (!free) continue;
        const face = label.face ? screen(label.face) : null;
        const outline = (label.corners || []).map(screen).filter(Boolean);
        const { x, y, dx } = pastOutline(free, face, outline, OFFSET_PX);
        const out = { text: label.text, at: label.at, x, y, align: dx < 0 ? "right" : "left", width: measure(label.text) };
        const endAt = label.end ? screen(label.end.at) : null;
        const endFace = endAt && label.end.face ? screen(label.end.face) : null;
        // At the arrow's outer end, `gap` px on along its line.
        const endBy = endAt ? (gap) => ({ ...out, at: label.end.at, ...besideEnd(endAt, endFace, gap, LINE_PX) }) : null;
        candidates.push({ out, endBy, endAt });
      }
      const where = JSON.stringify(candidates.map(({ out, endAt }) => [out.text, Math.round(out.x), Math.round(out.y), endAt ? endAt.map(Math.round) : 0]));
      const due = where !== castFor && now - castAt >= HIDDEN_EVERY_MS;
      if (due) {
        castFor = where;
        castAt = now;
        raycaster ??= new runtime.THREE.Raycaster();
        // An arrow's end is used only where it is in sight (no part between the eye and it), its label slid on along
        // the arrow's line until it lies over nothing of the model: never a label inside a fin, a hole or behind the part.
        endClear = candidates.map(({ endBy, endAt }) => {
          if (!endBy || blocked(raycaster, endBy(OFFSET_PX).at, null, true)) return null;
          const first = endBy(OFFSET_PX);
          const run = Math.hypot(first.x - endAt[0], first.y - endAt[1]) || 1;
          const [dx, dy] = [(first.x - endAt[0]) / run, (first.y - endAt[1]) / run];
          const room = roomAlong(first.x, first.y, dx, dy, width, height, Math.abs(dx) * first.width + OFFSET_PX);
          // Halving on the label's near end, one ray a step; then the whole label, where it ends up, must lie clear.
          const slide = clearAlong((distance) => !overModel(raycaster, endBy(OFFSET_PX + distance), false), room, 5);
          return slide != null && !overModel(raycaster, endBy(OFFSET_PX + slide)) ? slide : null;
        });
      }
      // Inside the view, off the panels at the left and the colour bar at the foot, and off each other.
      const placed = settleLabels(candidates.map(({ out, endBy }, index) => (endBy && endClear[index] != null ? endBy(OFFSET_PX + endClear[index]) : out)), covers,
        { height: LINE_PX, bounds: { width, height } });
      if (due) {
        // Through where each label is drawn, to its depth: past the outline, the model hides none in practice.
        hidden = placed.map((label) => blocked(raycaster, label.at, label, false));
      }
      placed.forEach((label, index) => { label.hidden = hidden[index] === true; });
      const key = JSON.stringify([width, height, dpr, tones, placed.map(({ text, x, y, align, hidden: ghost }) => [text, Math.round(x), Math.round(y), align, ghost])]);
      if (key === painted) return;
      painted = key;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      context.font = `${FONT_SIZE} ${window.getComputedStyle(host).fontFamily || "sans-serif"}`;
      // A canvas resized forgets its font: measure with the one set now.
      measure = (text) => context.measureText(text).width || text.length * 6;
      context.textBaseline = "middle";
      context.lineJoin = "round";
      for (const { text, x, y, align, hidden: ghost } of placed) {
        context.globalAlpha = ghost ? GHOST_OPACITY : 1;
        context.textAlign = align;
        context.lineWidth = 3;
        context.strokeStyle = tones.halo;
        context.strokeText(text, x, y);
        context.fillStyle = tones.ink;
        context.fillText(text, x, y);
      }
      context.globalAlpha = 1;
    };
    frameId = window.requestAnimationFrame(paint);
    return () => {
      window.cancelAnimationFrame(frameId);
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [runtimeRef, hostRef]);
  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true" data-fea-load-labels="" />;
}
