/** Contact (lite): parts pressing on each other or on a rigid plane (planned viewer file; static's defaults until its track fills it). */
import { planned } from "./stub.js";

export default planned({
  name: "contact", tier: 3, word: "Contact", noun: "this load",
  checks: ["stress", "displacement", "contact_pressure"], markers: ["load", "fixture", "rigid_plane"],
});
