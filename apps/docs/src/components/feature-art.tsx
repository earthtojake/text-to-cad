import type { ReactNode, SVGProps } from "react";

/**
 * The homepage's Features pictures: one line drawing per feature (`features`, src/lib/content.ts),
 * of the file its tile names. Two parts run through them: the bracket the Parts tile's script
 * models, then draws, shows, flattens and checks for an order, and the housing the checks and the
 * printer take. Every drawing is set on one 240 by 150 sheet in three inks: the part (foreground), its
 * construction (muted) and what the feature adds (the brand blue; a finding is the destructive red).
 *
 * The strokes draw themselves in once, as a tile first scrolls into view (`FeaturesReveal`, the
 * `feature-*` rules in app/globals.css): `Draw` strokes trace in, `Late` ones after them, `Fade`
 * shapes and labels (dashed lines, text, fills) fade in. Reduced motion shows them drawn.
 */

type Stroke = SVGProps<SVGPathElement>;

// A stroke that traces in (pathLength 1 is what the dash animation measures in).
function Draw({ late, className = "", ...props }: Stroke & { late?: boolean }) {
  return <path pathLength={1} className={`${late ? "feature-draw-late" : "feature-draw"} ${className}`} {...props} />;
}

// Anything that fades in rather than traces: a dashed line, a fill, a label.
function Fade({ late, children }: { late?: boolean; children: ReactNode }) {
  return <g className={late ? "feature-fade-late" : "feature-fade"}>{children}</g>;
}

// The sheet every drawing is on, cropped to the drawing (`view`) so each fills its tile. Groups set
// the ink; strokes take it as currentColor.
// `narrow` caps a drawing that carries running text, so its text never outgrows the tile's own.
function Sheet({ view, narrow, children }: { view: string; narrow?: boolean; children: ReactNode }) {
  return (
    <svg
      viewBox={view}
      aria-hidden="true"
      focusable="false"
      className={`h-full w-full ${narrow ? "max-w-[280px]" : "max-w-full"}`}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

const ink = "text-foreground/80";
const faint = "text-muted-foreground/70";
const accent = "text-brand";
const flag = "text-destructive";
const label = { fontSize: 9, fontFamily: "var(--font-mono)", stroke: "none", fill: "currentColor" } as const;

// The bracket in isometric: plate, wall and the hole through the plate, as scripts/gen made the
// path data (x right-down, y left-down, z up; 60 x 40 x 44 mm).
function IsoBracket({ size }: { size: "large" | "small" }) {
  const p =
    size === "large"
      ? {
          outline: "M131.7 138.4 L178.5 111.5 L178.5 52 L108.3 11.5 L103.6 14.3 L103.6 68.3 L61.5 92.5 L61.5 98 Z",
          creases: "M61.5 92.5 L131.7 133.1 M131.7 133.1 L131.7 138.4 M131.7 133.1 L173.8 108.8 M173.8 108.8 L173.8 54.8 M103.6 68.3 L173.8 108.8 M103.6 14.3 L173.8 54.8",
          hole: "M106.4 103.3 A6.6 3.8 0 1 1 119.6 103.3 A6.6 3.8 0 1 1 106.4 103.3 Z",
          inner: "M108.4 106 A6.6 3.8 0 0 1 117.6 106",
          axis: "M113 84.5 L113 125",
        }
      : {
          outline: "M148.2 121.7 L181.1 102.7 L181.1 60.9 L131.8 32.4 L128.5 34.3 L128.5 72.3 L98.9 89.3 L98.9 93.2 Z",
          creases: "M98.9 89.3 L148.2 117.8 M148.2 117.8 L148.2 121.7 M148.2 117.8 L177.8 100.8 M177.8 100.8 L177.8 62.8 M128.5 72.3 L177.8 100.8 M128.5 34.3 L177.8 62.8",
          hole: "M130.4 97 A4.7 2.7 0 1 1 139.8 97 A4.7 2.7 0 1 1 130.4 97 Z",
          inner: "M131.8 98.9 A4.7 2.7 0 0 1 138.4 98.9",
          axis: "M135.1 83.7 L135.1 112.2",
        };
  return (
    <>
      <g className={ink}>
        <Draw d={p.outline} strokeWidth={1.4} />
        <Draw d={p.creases} strokeWidth={1} />
        <Draw d={p.hole} strokeWidth={1} />
        <Draw d={p.inner} strokeWidth={0.8} />
      </g>
      {size === "large" ? (
        <g className={accent}>
          <Fade late>
            <path d={p.axis} strokeWidth={1} strokeDasharray="5 2 1 2" />
          </Fade>
        </g>
      ) : null}
    </>
  );
}

function PartsArt() {
  return (
    <Sheet view="52 4 136 142">
      <IsoBracket size="large" />
    </Sheet>
  );
}

// A two-layer sensor board: the outline and mounting holes, U1 and J1, and the routes the agent laid
// between them, octolinear, with one connection left to route (the dashed ratsnest line).
function BoardsArt() {
  const pads = [0, 1, 2, 3, 4];
  return (
    <Sheet view="20 10 200 130">
      <g className={ink}>
        <Draw d="M36 18 H204 A8 8 0 0 1 212 26 V124 A8 8 0 0 1 204 132 H36 A8 8 0 0 1 28 124 V26 A8 8 0 0 1 36 18 Z" strokeWidth={1.4} />
        {[[40, 30], [200, 30], [40, 120], [200, 120]].map(([x, y]) => (
          <Draw key={`${x}-${y}`} d={`M${x - 4} ${y} a4 4 0 1 0 8 0 a4 4 0 1 0 -8 0`} strokeWidth={1} />
        ))}
        {/* U1: a QFN with five pads a side. */}
        <Draw d="M72 52 H106 V86 H72 Z" strokeWidth={1.1} />
      </g>
      <g className={faint}>
        <Fade>
          {pads.map((i) => (
            <g key={i}>
              <rect x={75.5 + i * 6} y={46} width={3} height={5} rx={0.6} fill="currentColor" stroke="none" />
              <rect x={75.5 + i * 6} y={87} width={3} height={5} rx={0.6} fill="currentColor" stroke="none" />
              <rect x={66} y={56.5 + i * 6} width={5} height={3} rx={0.6} fill="currentColor" stroke="none" />
              <rect x={107} y={56.5 + i * 6} width={5} height={3} rx={0.6} fill="currentColor" stroke="none" />
            </g>
          ))}
          {/* J1, a four-pin header, pin 1 square; C1 and C2. */}
          <rect x={182} y={48} width={8} height={8} rx={1} strokeWidth={1.2} />
          {[64, 76, 88].map((y) => (
            <circle key={y} cx={186} cy={y} r={4} strokeWidth={1.2} />
          ))}
          {[52, 64, 76, 88].map((y) => (
            <circle key={y} cx={186} cy={y} r={1.4} fill="currentColor" stroke="none" />
          ))}
          <rect x={126} y={36.5} width={5} height={7} rx={0.8} fill="currentColor" stroke="none" />
          <rect x={136} y={36.5} width={5} height={7} rx={0.8} fill="currentColor" stroke="none" />
          <rect x={126} y={96.5} width={5} height={7} rx={0.8} fill="currentColor" stroke="none" />
          <rect x={136} y={96.5} width={5} height={7} rx={0.8} fill="currentColor" stroke="none" />
          <text x={83} y={72} style={{ ...label, fontSize: 7 }}>U1</text>
          <text x={181} y={104} style={{ ...label, fontSize: 7 }}>J1</text>
          <text x={128} y={33} style={{ ...label, fontSize: 6 }}>C1</text>
          <text x={128} y={112} style={{ ...label, fontSize: 6 }}>C2</text>
          {/* The connection still to route. */}
          <path d="M141 100 L182 88" strokeWidth={0.8} strokeDasharray="2 2" />
        </Fade>
      </g>
      <g className={accent} strokeWidth={2.2}>
        <Draw late d="M112 58 H140 L146 52 H182" />
        <Draw late d="M112 64 H182" />
        <Draw late d="M112 76 H182" />
        <Draw late d="M112 82 H140 L146 88 H182" />
        <Draw late d="M89 46 V40 H126" />
        <Draw late d="M83 92 V100 H126" />
        <Draw late d="M66 70 H58 L52 76 V96" />
      </g>
      <g className={accent}>
        <Fade late>
          <circle cx={52} cy={100} r={3.6} strokeWidth={1.4} />
          <circle cx={52} cy={100} r={1.2} fill="currentColor" stroke="none" />
        </Fade>
      </g>
    </Sheet>
  );
}

// A section through the housing, hatched: a 0.8 mm wall under the process's minimum, and an
// overhang past the 45-degree line a printer can build without supports.
function ChecksArt() {
  return (
    <Sheet view="14 30 222 100">
      <defs>
        <pattern id="feature-hatch" width={5} height={5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1={0} y1={0} x2={0} y2={5} className="text-muted-foreground" stroke="currentColor" strokeWidth={0.6} strokeOpacity={0.6} />
        </pattern>
      </defs>
      <Fade>
        <path d="M36 50 H64 V112 H173 V50 H176 V120 H56 V56 H36 Z" fill="url(#feature-hatch)" stroke="none" />
      </Fade>
      <g className={ink}>
        <Draw d="M36 50 H64 V112 H173 V50 H176 V120 H56 V56 H36 Z" strokeWidth={1.3} />
      </g>
      <g className={accent}>
        <Fade late>
          <path d="M56 56 L30 82" strokeWidth={1} strokeDasharray="3 2" />
          <text x={22} y={95} style={{ ...label, fontSize: 6.5 }}>45°</text>
        </Fade>
      </g>
      <g className={flag}>
        <Draw late d="M170 44 H179 A3 3 0 0 1 182 47 V88 A3 3 0 0 1 179 91 H170 A3 3 0 0 1 167 88 V47 A3 3 0 0 1 170 44 Z" strokeWidth={1.2} />
        <Draw late d="M36 59 H56" strokeWidth={2} />
        <Fade late>
          <path d="M182 60 H190" strokeWidth={1} />
          <text x={192} y={58} style={{ ...label, fontSize: 6.5 }}>0.8 mm</text>
          <text x={192} y={67} style={{ ...label, fontSize: 6.5 }}>min 1.2</text>
          <text x={22} y={44} style={{ ...label, fontSize: 6.5 }}>overhang</text>
        </Fade>
      </g>
    </Sheet>
  );
}

// The bracket's drawing sheet: front view with the hole hidden, top view with its centre mark, the
// side view's L, dimensions, a hole callout and the title block.
function DrawingsArt() {
  const arrow = (x: number, y: number, dir: "l" | "r" | "u" | "d") => {
    const d = { l: `M${x + 3} ${y - 1.5} L${x} ${y} L${x + 3} ${y + 1.5}`, r: `M${x - 3} ${y - 1.5} L${x} ${y} L${x - 3} ${y + 1.5}`, u: `M${x - 1.5} ${y + 3} L${x} ${y} L${x + 1.5} ${y + 3}`, d: `M${x - 1.5} ${y - 3} L${x} ${y} L${x + 1.5} ${y - 3}` }[dir];
    return <path d={d} strokeWidth={0.8} />;
  };
  return (
    <Sheet view="4 2 232 146">
      <g className={faint}>
        <Draw d="M8 6 H232 V144 H8 Z" strokeWidth={0.8} />
        <Draw d="M13 11 H227 V139 H13 Z" strokeWidth={0.6} />
        <Draw d="M152 114 H227 M152 114 V139 M190 114 V139 M152 126.5 H227" strokeWidth={0.6} />
        <Fade>
          <text x={156} y={123} style={{ ...label, fontSize: 6.5 }}>bracket</text>
          <text x={194} y={123} style={{ ...label, fontSize: 6.5 }}>steel</text>
          <text x={156} y={135} style={{ ...label, fontSize: 6.5 }}>1:1 mm</text>
          <text x={194} y={135} style={{ ...label, fontSize: 6.5 }}>ISO A4</text>
          {/* Centre mark through the hole in the top view. */}
          <path d="M50.5 99 H66.5 M58.5 91 V107" strokeWidth={0.5} strokeDasharray="4 1.5 1 1.5" />
          {/* The hole, hidden, in the front and side views. */}
          <path d="M54.7 60 V63.8 M62.3 60 V63.8 M122.9 60 V63.8 M130.5 60 V63.8" strokeWidth={0.7} strokeDasharray="1.5 1" />
        </Fade>
      </g>
      <g className={ink}>
        {/* Front view, top view, side view. */}
        <Draw d="M30 22 H87 V63.8 H30 Z M30 60 H87" strokeWidth={1.1} />
        <Draw d="M30 75 H87 V113 H30 Z M30 78.8 H87" strokeWidth={1.1} />
        <Draw d="M58.5 95.2 a3.8 3.8 0 1 0 0.01 0" strokeWidth={1} />
        <Draw d="M102 22 H105.8 V60 H140 V63.8 H102 Z" strokeWidth={1.1} />
      </g>
      <g className={accent}>
        <Fade late>
          <path d="M30 116 V124 M87 116 V124 M30 121 H87" strokeWidth={0.6} />
          {arrow(30, 121, "l")}
          {arrow(87, 121, "r")}
          <text x={53} y={131} style={label}>60</text>
          <path d="M27 22 H19 M27 63.8 H19 M22 22 V63.8" strokeWidth={0.6} />
          {arrow(22, 22, "u")}
          {arrow(22, 63.8, "d")}
          <text x={15} y={46} style={label} transform="rotate(-90 15 46)" textAnchor="middle">44</text>
          <path d="M102 67 V75 M140 67 V75 M102 72 H140" strokeWidth={0.6} />
          {arrow(102, 72, "l")}
          {arrow(140, 72, "r")}
          <text x={116} y={82} style={label}>40</text>
          <path d="M61.2 101.7 L70 107 H104" strokeWidth={0.6} />
          <text x={72} y={105} style={label}>⌀8 thru</text>
        </Fade>
      </g>
    </Sheet>
  );
}

// The CAD Viewer over the bracket: the panel at the left, the tool strip with Measure in hand, a
// measurement along the plate's front edge, and the view cube.
function ViewerArt() {
  return (
    <Sheet view="8 4 224 142">
      <g className={faint}>
        <Draw d="M18 8 H222 A6 6 0 0 1 228 14 V136 A6 6 0 0 1 222 142 H18 A6 6 0 0 1 12 136 V14 A6 6 0 0 1 18 8 Z" strokeWidth={1} />
        <Draw d="M54 8 V142" strokeWidth={0.8} />
        <Fade>
          <path d="M19 22 H44 M23 34 H47 M23 46 H40 M19 58 H45" strokeWidth={1.6} />
          <rect x={115} y={15} width={58} height={13} rx={6.5} strokeWidth={0.9} />
          {[125, 137, 161].map((x) => (
            <circle key={x} cx={x} cy={21.5} r={2.4} fill="currentColor" stroke="none" />
          ))}
          {/* The view cube. */}
          <path d="M205 107 L214.5 112.5 V123.5 L205 129 L195.5 123.5 V112.5 Z M205 118 L195.5 112.5 M205 118 L214.5 112.5 M205 118 V129" strokeWidth={0.9} />
        </Fade>
      </g>
      <g className={accent}>
        <Fade>
          <rect x={16} y={28} width={35} height={12} rx={3} fill="currentColor" fillOpacity={0.14} stroke="none" />
          <circle cx={149} cy={21.5} r={2.4} fill="currentColor" stroke="none" />
        </Fade>
      </g>
      <IsoBracket size="small" />
      <g className={accent}>
        <Draw late d="M85.7 100.8 L135 129.3" strokeWidth={1.2} />
        <Fade late>
          <path d="M98.9 93.2 L84.2 101.7 M148.2 121.7 L133.5 130.2" strokeWidth={0.6} />
          <circle cx={98.9} cy={93.2} r={2} fill="currentColor" stroke="none" />
          <circle cx={148.2} cy={121.7} r={2} fill="currentColor" stroke="none" />
          <rect x={92} y={108} width={32} height={13} rx={6.5} fill="currentColor" stroke="none" />
          <text x={108} y={117.5} style={{ ...label, fill: "var(--background)" }} textAnchor="middle">60 mm</text>
        </Fade>
      </g>
    </Sheet>
  );
}

// The bracket unfolded: the cut outline and the hole on the cut layer, the bend on its own layer.
function CutArt() {
  return (
    <Sheet view="60 22 120 122">
      <g className={ink}>
        <Draw d="M72 39 H168 V111 H72 Z" strokeWidth={1.4} />
        <Draw d="M148.8 70.2 a4.8 4.8 0 1 0 0.01 0" strokeWidth={1.2} />
      </g>
      <g className={accent}>
        <Fade late>
          <path d="M120 33 V117" strokeWidth={1.2} strokeDasharray="6 3" />
          <text x={124} y={31} style={{ ...label, fontSize: 7.5 }}>bend 90°</text>
        </Fade>
      </g>
      <Fade late>
        <g className={ink}>
          <path d="M72 134 H86" strokeWidth={1.4} />
          <text x={90} y={137} style={{ ...label, fontSize: 7.5 }}>cut</text>
        </g>
        <g className={accent}>
          <path d="M116 134 H130" strokeWidth={1.2} strokeDasharray="4 2" />
          <text x={134} y={137} style={{ ...label, fontSize: 7.5 }}>bend</text>
        </g>
      </Fade>
    </Sheet>
  );
}

// The same flat pattern, read against SendCutSend's guide: the checks a preflight report makes.
function SendCutSendArt() {
  const checks = ["Units and scale", "Closed contours", "Bend lines", "Material, thickness"];
  return (
    <Sheet view="10 30 222 84" narrow>
      <g className={ink}>
        <Draw d="M16 48 H88 V102 H16 Z" strokeWidth={1.3} />
        <Draw d="M74 71.4 a3.6 3.6 0 1 0 0.01 0" strokeWidth={1} />
      </g>
      <g className={accent}>
        <Fade>
          <path d="M52 44 V106" strokeWidth={1} strokeDasharray="5 2.5" />
        </Fade>
      </g>
      {checks.map((text, i) => (
        <g key={text}>
          <g className={accent}>
            <Draw late d={`M106 ${44 + i * 20} a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0`} strokeWidth={1.1} />
            <Draw late d={`M109 ${44 + i * 20} l2 2.2 l4 -4.4`} strokeWidth={1.4} />
          </g>
          <g className={ink}>
            <Fade late>
              <text x={124} y={47 + i * 20} style={{ ...label, fontFamily: "var(--font-sans)", fontSize: 10 }}>{text}</text>
            </Fade>
          </g>
        </g>
      ))}
    </Sheet>
  );
}

// The housing on the bed, layer by layer, the nozzle laying the next one.
function PrintArt() {
  const walls = [80, 84, 88, 92, 96, 100, 104, 108, 112];
  return (
    <Sheet view="30 18 180 112">
      <g className={faint}>
        <Draw d="M36 124.5 H204" strokeWidth={1.4} />
        <Fade>
          <path d={`${walls.map((y) => `M64 ${y} H72 M168 ${y} H176`).join(" ")} M64 116 H176 M64 120 H176`} strokeWidth={0.6} />
        </Fade>
      </g>
      <g className={ink}>
        <Draw d="M64 76 V124 H176 V76 H168 V112 H72 V76 Z" strokeWidth={1.3} />
        {/* The hotend: heat break, heater block, nozzle. */}
        <Draw d="M168 26 H176 V42 H168 Z M158 42 H186 V58 H158 Z M166 58 H178 L174 67 H170 Z" strokeWidth={1.1} />
      </g>
      <g className={accent}>
        <Draw late d="M64 72 H72 M168 72 H172" strokeWidth={2.6} />
      </g>
    </Sheet>
  );
}

// A three-joint arm: base, shoulder, elbow, wrist and gripper, each revolute joint's axis out of the
// page, and the shoulder's limits.
function RobotsArt() {
  return (
    <Sheet view="22 14 196 116">
      <g className={faint}>
        <Draw d="M28 120 H212" strokeWidth={1.2} />
        <Fade>
          <path d={Array.from({ length: 18 }, (_, i) => `M${34 + i * 10} 120 l-5 5`).join(" ")} strokeWidth={0.6} />
          <text x={64} y={62} style={{ ...label, fontSize: 7 }} textAnchor="end">shoulder</text>
          <text x={128} y={26} style={{ ...label, fontSize: 7 }}>elbow</text>
          <text x={186} y={56} style={{ ...label, fontSize: 7 }}>wrist</text>
        </Fade>
      </g>
      <g className={ink}>
        <Draw d="M58 120 L64 106 H92 L98 120" strokeWidth={1.3} />
        <Draw d="M86 104 L86 64 A8 8 0 0 0 70 64 L70 104 A8 8 0 0 0 86 104 Z" strokeWidth={1.3} />
        <Draw d="M80.4 70 L140.4 46 A6.5 6.5 0 0 0 135.6 34 L75.6 58 A6.5 6.5 0 0 0 80.4 70 Z" strokeWidth={1.3} />
        <Draw d="M135.3 44.2 L175.3 70.2 A5 5 0 0 0 180.7 61.8 L140.7 35.8 A5 5 0 0 0 135.3 44.2 Z" strokeWidth={1.3} />
        <Draw d="M180.3 77.1 L189.1 63.7 M180.3 77.1 L188.7 82.5 M189.1 63.7 L197.5 69.1" strokeWidth={1.3} />
      </g>
      <g className={accent}>
        {[[78, 104, 5], [78, 64, 5], [138, 40, 4.5], [178, 66, 4]].map(([x, y, r]) => (
          <g key={`${x}-${y}`}>
            <Draw late d={`M${x - r} ${y} a${r} ${r} 0 1 0 ${2 * r} 0 a${r} ${r} 0 1 0 ${-2 * r} 0`} strokeWidth={1.2} />
          </g>
        ))}
        <Fade late>
          {[[78, 104], [78, 64], [138, 40], [178, 66]].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={1.3} fill="currentColor" stroke="none" />
          ))}
          <path d="M90 43.2 A24 24 0 0 1 101.2 70.2" strokeWidth={1} strokeDasharray="3 2" />
        </Fade>
      </g>
    </Sheet>
  );
}

const ART: Record<string, () => ReactNode> = {
  parts: PartsArt,
  boards: BoardsArt,
  checks: ChecksArt,
  drawings: DrawingsArt,
  viewer: ViewerArt,
  cut: CutArt,
  sendcutsend: SendCutSendArt,
  print: PrintArt,
  robots: RobotsArt,
};

export function FeatureArt({ id }: { id: string }) {
  const Art = ART[id];
  return Art ? <Art /> : null;
}
