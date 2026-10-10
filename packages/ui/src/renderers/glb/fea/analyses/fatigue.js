/** Fatigue life: life in cycles and the fatigue safety factor (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "fatigue", tier: 1, word: "Fatigue life", noun: "this load",
  checks: ["fatigue"], markers: ["load", "fixture", "body_load"],
});
