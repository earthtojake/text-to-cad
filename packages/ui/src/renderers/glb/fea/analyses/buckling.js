/** Buckling: how many times this load before it buckles (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

// The Load ramp, as buckling says it: the load going on until the shape gives.
const BUCKLE = Object.freeze({ id: "fea:buckle", label: "Buckle", kind: "load_ramp" });

export default planned({
  name: "buckling", tier: 1, word: "Buckling", noun: "this load", scalesWithLoad: true,
  checks: ["buckling"], routine: () => BUCKLE, markers: ["load", "fixture"],
});
