// Wheel zoom speeds are exponents, not multipliers: OrbitControls r161+ scales the camera
// distance by 0.95 ^ (zoomSpeed * |deltaY| / 100), with deltaY already normalized for
// deltaMode. A standard mouse notch is |deltaY| = 100, so a speed of N means one notch moves
// the camera by 0.95^N -- 2.5 is about -12%. Before r161 the same expression also divided by
// floor(devicePixelRatio), which made every one of these numbers mean something different on
// a 1x display than on a Retina one; that division is gone, so they are display-independent.
export const DEFAULT_ZOOM_SPEED = 4.5;

export const COARSE_POINTER_ZOOM_SPEED = 1.6;

// 5.0, not 2.5. The r161 upgrade removed OrbitControls' divide-by-devicePixelRatio, and I
// retuned this against a single mouse notch without checking what else runs through it. A
// trackpad flick does: isTrackpadLikeWheelEvent only claims deltas under 20, and momentum
// carries an ordinary two-finger scroll well past that, so most of a gesture lands here.
// 2.5 halved it. 5.0 restores exactly what a Retina Mac had before r161 -- 0.95^(5*d/100) is
// the same curve as the old 0.95^(10*d/200) -- and every display now gets that same curve
// instead of only the 2x ones.
export const ACCELERATED_WHEEL_ZOOM_SPEED = 5.0;

export const TRACKPAD_PINCH_ZOOM_SPEED = 7;

export const COARSE_POINTER_PINCH_ZOOM_SPEED = 2.4;
