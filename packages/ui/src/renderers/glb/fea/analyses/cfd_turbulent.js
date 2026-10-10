/**
 * Turbulent flow (lite): steady RANS (k-omega SST, wall functions, incompressible) through or around the
 * part, Tier 3: the step up from Flow (`cfd`) past the laminar range. It writes what Flow writes: the wall
 * pressure (Pa, signed) and the wall shear (the wall function's) on the part's wetted surface, and, mapped
 * onto the structure (one-way), the part's stress and displacement, so it deforms. Its verdict judges the
 * pressure drop and the fastest flow (and the stress and displacement when mapped), none of which a load
 * control moves, and its takeaway leads with "RANS · " (never Flow's "unreliable above Re", which is the
 * laminar solver's warning). What you see, its setup and its markers are Flow's. It plays no routine.
 */
import { FLOW_SETUP, flowControls } from "./cfd.js";
import { planned } from "./stub.js";

export default planned({
  name: "cfd_turbulent", tier: 3, word: "Turbulent flow", noun: "this flow", limitWord: "RANS", family: null, scalesWithLoad: false,
  checks: ["pressure_drop", "velocity", "stress", "displacement"],
  defaultControls: flowControls,
  setupGroups: FLOW_SETUP,
  routine: () => null,
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings",
});
