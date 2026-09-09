import { describe, expect, it } from "vitest";

import {
  TITLEBAR_HEIGHT,
  TRAFFIC_LIGHTS_INSET,
  TRAFFIC_LIGHT_DIAMETER,
  TRAFFIC_LIGHT_X,
  titlebarInset,
  trafficLightPosition,
} from "@shared/titlebar";

describe("trafficLightPosition", () => {
  it("centres the cluster in the strip", () => {
    const { x, y } = trafficLightPosition();
    expect(x).toBe(TRAFFIC_LIGHT_X);
    // Equal room above and below: the app's own buttons in that row are
    // centred the same way, so the two lines of controls read as one.
    expect(y).toBe((TITLEBAR_HEIGHT - TRAFFIC_LIGHT_DIAMETER) / 2);
    expect(y + TRAFFIC_LIGHT_DIAMETER + y).toBe(TITLEBAR_HEIGHT);
  });

  it("follows the strip's height", () => {
    expect(trafficLightPosition(48).y).toBe(18);
    // A height that does not divide evenly still lands on a whole pixel.
    expect(trafficLightPosition(37).y).toBe(13);
  });
});

describe("titlebarInset", () => {
  it("falls back to the measured constant when there is nothing to read", () => {
    // The frame before the first measurement, and any window without the
    // overlay: reserving nothing would put a control under the lights.
    expect(titlebarInset(null)).toBe(TRAFFIC_LIGHTS_INSET);
    expect(titlebarInset(undefined)).toBe(TRAFFIC_LIGHTS_INSET);
  });

  it("reserves nothing when the controls are not there", () => {
    // Fullscreen: macOS takes the buttons away, so the strip keeps its room.
    expect(titlebarInset({ visible: false, x: 84 })).toBe(0);
  });

  it("takes the measurement over the constant", () => {
    // A macOS that draws the cluster wider moves the app's controls with it.
    expect(titlebarInset({ visible: true, x: 96 })).toBe(96);
    expect(titlebarInset({ visible: true, x: 92.4 })).toBe(92);
  });

  it("keeps the constant when a visible overlay reports nothing", () => {
    // Reported visible and zero wide is not a measurement; it is a reading
    // taken before the geometry settled, and trusting it is an overlap.
    expect(titlebarInset({ visible: true, x: 0 })).toBe(TRAFFIC_LIGHTS_INSET);
  });
});
