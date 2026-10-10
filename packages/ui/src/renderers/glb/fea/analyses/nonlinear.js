/** Permanent bend / Stretch (lite): plasticity or rubber, load-stepped (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const PLAY = routineOf("Play", "play");

export default planned({
  name: "nonlinear", tier: 3, word: "Permanent bend", noun: "this load",
  checks: ["plastic_strain", "displacement", "stress"], routine: (result) => (result?.series ? PLAY : null),
  markers: ["load", "fixture", "body_load"],
});
