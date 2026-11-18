// The viewer's orbit: a turntable that goes over the top. A sideways drag turns the camera about
// the world's vertical (z) through the orbit target; an up-and-down drag turns it about its own
// right, which is always level, through the target, with no limit: past straight down or straight
// up it goes on, and the view comes round upside down. Turned about nothing but those two axes, the
// camera never rolls: it is upright, or upside down, exactly. So its up is its own (`camera.up`,
// square to the view), never the world's: an upside-down camera's points down the world.
//
// While the view is upside down a sideways drag turns the other way, so the near side of the model
// still follows the cursor. Which way is picked as the drag starts, from the camera as it is then,
// and held to its end: a drag that carries the view over a pole never reverses under the cursor.
// The next drag picks again. The arrow keys and the cube's drag turn the same way
// (`viewportCameraKit.js`'s `applyOrbitDelta`), each holding its sense for its own gesture.
//
// three's OrbitControls keeps everything else (pan, the wheel and the pinch, zoom to the cursor,
// damping, touch): only its rotation is replaced. Its own turns the camera about `camera.up` as its
// constructor found it, clamps the angle from that axis to [0, π], and rebuilds the camera from that
// angle on every update, where `Spherical.makeSafe()` moves a camera straight down the axis off it.

// How far the screen's up may lean below level and still read as upright: a camera turned to a pole
// exactly (a top or bottom view) is upright, as those views always were.
const UPRIGHT_SLACK = 1e-9;
// A view this near the world's vertical (the sine of its angle off it) is straight down or up it,
// where every direction square to the view is level and the camera's own right is the one.
const POLE = 1e-6;

const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const unit = (v) => {
  const length = Math.hypot(v[0], v[1], v[2]);
  return length > 1e-12 ? [v[0] / length, v[1] / length, v[2] / length] : null;
};
const square = (v, to) => { const along = dot(v, to); return [v[0] - along * to[0], v[1] - along * to[1], v[2] - along * to[2]]; };
/** `v` turned by `angle` about the unit `axis` (Rodrigues). */
function turned(v, axis, angle) {
  const cos = Math.cos(angle), sin = Math.sin(angle), k = cross(axis, v), along = dot(axis, v) * (1 - cos);
  return [0, 1, 2].map((i) => v[i] * cos + k[i] * sin + axis[i] * along);
}
/** `(0, 1, 0)` turned by a three.js quaternion: the camera's up as its orientation has it. */
function orientationUp({ x, y, z, w }) {
  return [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)];
}

/**
 * The camera's frame about `target`, level: how far the eye stands (`distance`), the way back from
 * the target to it (`back`), its `right`, square to the view and to the world's vertical on the side
 * the camera's own right is, and its `up` (`back × right`), each a unit `[x, y, z]`. The camera's own
 * up is `camera.up` square to the view, or its orientation's where `camera.up` runs along the view. A
 * camera handed in rolled is read level. Null for a camera on its target.
 */
export function cameraFrame(camera, target) {
  const position = camera?.position;
  if (!position || !target) return null;
  const offset = [position.x - target.x, position.y - target.y, position.z - target.z];
  const distance = Math.hypot(...offset);
  if (!(distance > 1e-12)) return null;
  const back = offset.map((value) => value / distance);
  const up = unit(square(camera.up ? [camera.up.x, camera.up.y, camera.up.z] : [0, 0, 1], back))
    || (camera.quaternion && unit(square(orientationUp(camera.quaternion), back)))
    || unit(square([0, 0, 1], back)) || [0, 1, 0];
  let right = cross(up, back);
  const level = [-back[1], back[0], 0]; // z × back
  const levelLength = Math.hypot(level[0], level[1]);
  if (levelLength > POLE) {
    const side = dot(right, level) < 0 ? -1 : 1;
    right = [side * level[0] / levelLength, side * level[1] / levelLength, 0];
  } else {
    right = unit([right[0], right[1], 0]) || [1, 0, 0];
  }
  return { distance, back, right, up: unit(cross(back, right)) };
}

/**
 * Whether a sideways turn goes the plain way (1) or the other (-1): the other while the camera is
 * upside down, its up pointing down the world, so the near side of the model still follows the
 * cursor. Read off the camera level (`cameraFrame`); a camera straight down or up is upright.
 */
export function turnSense(camera, target) {
  const frame = cameraFrame(camera, target);
  return frame && frame.up[2] < -UPRIGHT_SLACK ? -1 : 1;
}

/**
 * Turns `camera` about `target`: `sideways` radians about the world's vertical (positive is
 * anticlockwise seen from above), then `vertical` radians about its own level right (positive takes
 * the eye toward the screen's bottom), unclamped. Sets its position and its up (square to the view,
 * level); its orientation is the caller's `lookAt`. A camera handed in rolled comes out level.
 * @returns {boolean} False for a camera on its target, which nothing turns.
 */
export function turnCamera(camera, target, sideways = 0, vertical = 0) {
  const frame = cameraFrame(camera, target);
  if (!frame) return false;
  let { back, right } = frame;
  if (sideways) {
    back = turned(back, [0, 0, 1], sideways);
    right = turned(right, [0, 0, 1], sideways);
  }
  if (vertical) back = unit(turned(back, right, vertical)) || back;
  const up = unit(cross(back, right)) || frame.up;
  camera.position.set(target.x + back[0] * frame.distance, target.y + back[1] * frame.distance, target.z + back[2] * frame.distance);
  camera.up.set(...up);
  return true;
}

/** The camera's up set level where it stands (`cameraFrame`), its position kept. */
export function levelCamera(camera, target) {
  const frame = cameraFrame(camera, target);
  if (!frame || !camera.up) return false;
  camera.up.set(...frame.up);
  return true;
}

const turntableClasses = new WeakMap();

/**
 * `OrbitControls`, turning as the turntable does. Its rotation's two inputs, `_rotateLeft` (a
 * sideways drag, a finger's, Preview's Orbit) and `_rotateUp` (an up-and-down one), add to a turn
 * still to make, which `update` makes a share of at a time, as three makes its own: the whole of it
 * without damping, `dampingFactor` of what is left with, the rest carried on as the camera's inertia.
 * Pan, zoom and their damping stay three's. The polar and azimuth limits are not kept: the turntable
 * has none.
 */
export function turntableOrbitControls(OrbitControls) {
  let Turntable = turntableClasses.get(OrbitControls);
  if (!Turntable) {
    Turntable = class extends OrbitControls {
      // three's constructor calls `update()` before a subclass's own fields could exist, so the
      // state below is made where it is first used, never as class fields.
      constructor(...args) {
        super(...args);
        // A gesture's sideways sense, held from its start to its end (`turnSense`); Preview's Orbit
        // turns between gestures, the plain way.
        this.addEventListener("start", () => { this._turnSense = turnSense(this.object, this.target); });
        this.addEventListener("end", () => { this._turnSense = 1; });
      }

      _pendingTurn() {
        this._turn ||= { sideways: 0, vertical: 0 };
        return this._turn;
      }

      _rotateLeft(angle) {
        this._pendingTurn().sideways -= angle * (this._turnSense || 1);
      }

      _rotateUp(angle) {
        this._pendingTurn().vertical -= angle;
      }

      update(deltaTime = null) {
        const turn = this._turn;
        if (turn && (turn.sideways || turn.vertical)) {
          const share = this.enableDamping ? this.dampingFactor : 1;
          turnCamera(this.object, this.target, turn.sideways * share, turn.vertical * share);
          turn.sideways *= 1 - share;
          turn.vertical *= 1 - share;
        }
        // three rebuilds the camera from its angles about an axis of its own (`_quat` takes that axis to
        // +y) on every update. About the camera's own level right, the view lies on that axis's equator,
        // where the rebuild gives back exactly the camera it was given: a view straight down the world's
        // vertical stays exactly there, which about the world's vertical `makeSafe()` would move.
        const frame = cameraFrame(this.object, this.target);
        if (frame && this._quat && this._quatInverse) {
          this._turnAxis ||= this.target.clone();
          this._turnPole ||= this.target.clone().set(0, 1, 0);
          this._quat.setFromUnitVectors(this._turnAxis.set(...frame.right), this._turnPole);
          this._quatInverse.copy(this._quat).invert();
        }
        return super.update(deltaTime);
      }

      disconnect() {
        // A gesture cut off by letting go of the page sends no `end`.
        this._turnSense = 1;
        super.disconnect();
      }
    };
    turntableClasses.set(OrbitControls, Turntable);
  }
  return Turntable;
}
