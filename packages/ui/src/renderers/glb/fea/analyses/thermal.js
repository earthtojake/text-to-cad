/** Heat: a steady temperature (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "thermal", tier: 1, word: "Heat", noun: "this heat",
  checks: ["temperature"], markers: ["temperature", "heat", "convection"], displayTitle: "Heat inputs and temperatures",
});
