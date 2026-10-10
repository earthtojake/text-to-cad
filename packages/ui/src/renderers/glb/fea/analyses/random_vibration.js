/** Random vibration: the response to a PSD, 1σ and 3σ (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "random_vibration", tier: 1, word: "Random vibration", noun: "this shake", scalesWithLoad: true,
  checks: ["stress", "displacement", "acceleration"], checkLabels: { stress: "Random vibration" },
  markers: ["fixture", "base_excitation"], displayTitle: "Shaker and fixtures",
});
