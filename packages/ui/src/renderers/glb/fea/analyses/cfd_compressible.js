/**
 * Fast gas flow (lite): steady compressible flow of an ideal gas through or around the part, Tier 3: the
 * step up from Flow (`cfd`) for a gas past about Mach 0.3, where its density changes with its speed. Its
 * fields are on the part's wetted surface: the wall pressure (Pa above the outlet's, signed), the Mach
 * number (the flow's speed over the local speed of sound) and the gas temperature; mapped onto the
 * structure (one-way), the part's stress and displacement join them and it deforms. Its verdict judges
 * the pressure drop, the fastest flow and the highest Mach number (and the stress and displacement when
 * mapped), none of which a load control moves, and its takeaway leads with "Ideal gas · ". What you see
 * opens on the field (Pressure first, then Mach number and Temperature) and, mapped, the deformation; its
 * setup and markers are Flow's. It plays no routine.
 */
import { FLOW_SETUP, flowControls } from "./cfd.js";
import { planned } from "./stub.js";

export default planned({
  name: "cfd_compressible", tier: 3, word: "Fast gas flow", noun: "this flow", limitWord: "Ideal gas", family: null, scalesWithLoad: false,
  checks: ["pressure_drop", "velocity", "mach", "stress", "displacement"],
  defaultControls: flowControls,
  setupGroups: FLOW_SETUP,
  routine: () => null,
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings",
});
