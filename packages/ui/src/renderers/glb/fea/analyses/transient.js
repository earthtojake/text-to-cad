/** Over time: a load against time, the peak response (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const PLAY = routineOf("Play", "play");

export default planned({
  name: "transient", tier: 1, word: "Over time", noun: "this load", scalesWithLoad: true,
  checks: ["stress", "displacement", "acceleration"], routine: (result) => (result?.series ? PLAY : null),
  markers: ["load", "fixture", "base_excitation"],
});
