/** Shaking: the response to a sine sweep (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const VIBRATE = routineOf("Vibrate", "vibrate");

export default planned({
  name: "harmonic", tier: 1, word: "Shaking", noun: "this shake", scalesWithLoad: true,
  checks: ["stress", "displacement", "acceleration"], routine: () => VIBRATE,
  markers: ["fixture", "base_excitation", "load"], displayTitle: "Shaker and fixtures",
});
