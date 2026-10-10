/** Drop (estimate): the equivalent static load of a drop (planned viewer file; static's defaults until its track fills it). */
import { LOAD_RAMP } from "./static.js";
import { planned } from "./stub.js";

export default planned({
  name: "drop", tier: 2, word: "Drop (estimate)", noun: "this drop", family: "static", estimate: true, scalesWithLoad: true,
  checks: ["stress", "displacement"], checkLabels: { stress: "Drop" }, routine: () => LOAD_RAMP,
  markers: ["drop", "fixture"],
});
