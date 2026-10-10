/** Vibration: natural frequencies and mode shapes (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const VIBRATE = routineOf("Vibrate", "vibrate");

export default planned({
  name: "modal", tier: 1, word: "Vibration", noun: "this load",
  checks: ["frequency"], routine: () => VIBRATE, markers: ["fixture"],
});
