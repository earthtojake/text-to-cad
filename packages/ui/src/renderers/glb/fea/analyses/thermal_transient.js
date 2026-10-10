/** Heat over time: temperature against time, the hottest moment (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const PLAY = routineOf("Play", "play");

export default planned({
  name: "thermal_transient", tier: 1, word: "Heat over time", noun: "this heat",
  checks: ["temperature"], routine: (result) => (result?.series ? PLAY : null),
  markers: ["temperature", "heat", "convection"], displayTitle: "Heat inputs and temperatures",
});
