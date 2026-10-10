/** Shock: the response to a shock spectrum (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "shock", tier: 1, word: "Shock", noun: "this shake", scalesWithLoad: true,
  checks: ["stress", "displacement", "acceleration"], checkLabels: { stress: "Shock" },
  markers: ["fixture", "base_excitation"], displayTitle: "Shaker and fixtures",
});
