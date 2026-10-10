/** Drop impact (lite): an explicit drop onto a rigid floor (planned viewer file; static's defaults until its track fills it). */
import { planned, routineOf } from "./stub.js";

const PLAY = routineOf("Play", "play");

export default planned({
  name: "impact", tier: 3, word: "Drop impact", noun: "this drop", limitWord: "Rigid floor",
  checks: ["stress", "displacement", "acceleration", "plastic_strain"], routine: (result) => (result?.series ? PLAY : null),
  markers: ["drop", "rigid_plane"],
});
