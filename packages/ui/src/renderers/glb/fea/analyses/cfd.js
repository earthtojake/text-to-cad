/** Flow (lite): steady laminar flow and the wall pressure on the part (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "cfd", tier: 3, word: "Flow", noun: "this flow", limitWord: "Laminar",
  checks: ["pressure_drop", "velocity", "stress", "displacement"],
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings",
});
