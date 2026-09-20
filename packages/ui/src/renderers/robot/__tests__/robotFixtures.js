// Robot descriptions for this folder's tests, parsed by core's own parsers (jsdom supplies
// the DOMParser a browser would). Primitives only: no mesh is fetched.
import { JSDOM } from "jsdom";
import { buildUrdfMeshGeometry } from "@hardcore/core/lib/urdf/kinematics.js";
import { parseSdf } from "@hardcore/core/lib/urdf/parseSdf.js";
import { parseSrdf } from "@hardcore/core/lib/urdf/parseSrdf.js";
import { parseUrdf } from "@hardcore/core/lib/urdf/parseUrdf.js";
import { buildRobotParts } from "../robotParts.js";

function withDom(read) {
  const previous = globalThis.DOMParser;
  globalThis.DOMParser = new JSDOM("").window.DOMParser;
  try { return read(); } finally { globalThis.DOMParser = previous; }
}

const box = (size, xyz = "0 0 0", rgba = "") => `<visual><origin xyz="${xyz}"/><geometry><box size="${size}"/></geometry>${rgba
  ? `<material name="m${rgba.replaceAll(" ", "")}"><color rgba="${rgba}"/></material>` : ""}</visual>`;

// base -(yaw, continuous Z)-> turret -(pitch, revolute Y, 1 m up)-> arm -(lift, prismatic Z)-> tool
// with a fixed camera, a mimic finger pair, and a wheel whose geometry sits on its own axis.
export const ARM_URDF = `<?xml version="1.0"?>
<robot name="arm">
  <link name="base">${box("0.6 0.6 0.1", "0 0 0.05", "0.3 0.3 0.35 1")}</link>
  <link name="turret">${box("0.2 0.2 1", "0 0 0.5")}</link>
  <link name="arm">${box("1 0.2 0.2", "0.5 0 0", "0.9 0.5 0.1 1")}</link>
  <link name="tool">${box("0.1 0.1 0.1")}</link>
  <link name="camera"/>
  <link name="finger_link">${box("0.02 0.02 0.1", "0 0.05 0.1")}</link>
  <link name="finger_mirror_link">${box("0.02 0.02 0.1", "0 -0.05 0.1")}</link>
  <link name="wheel_link"><visual><geometry><cylinder radius="0.3" length="0.1"/></geometry></visual></link>
  <joint name="yaw" type="continuous"><parent link="base"/><child link="turret"/><origin xyz="0 0 0.1"/><axis xyz="0 0 1"/></joint>
  <joint name="pitch" type="revolute"><parent link="turret"/><child link="arm"/><origin xyz="0 0 1" rpy="0 0 0.3"/><axis xyz="0 1 0"/><limit lower="-1.5708" upper="1.5708" effort="1" velocity="1"/></joint>
  <joint name="lift" type="prismatic"><parent link="arm"/><child link="tool"/><origin xyz="1 0 0"/><axis xyz="0 0 1"/><limit lower="0" upper="0.5" effort="1" velocity="1"/></joint>
  <joint name="camera_mount" type="fixed"><parent link="turret"/><child link="camera"/><origin xyz="0 0 1.2" rpy="0 0.5 0"/></joint>
  <joint name="finger" type="prismatic"><parent link="tool"/><child link="finger_link"/><axis xyz="0 1 0"/><limit lower="0" upper="0.04" effort="1" velocity="1"/></joint>
  <joint name="finger_mirror" type="prismatic"><parent link="tool"/><child link="finger_mirror_link"/><axis xyz="0 1 0"/><limit lower="-0.04" upper="0" effort="1" velocity="1"/><mimic joint="finger" multiplier="-1"/></joint>
  <joint name="wheel" type="continuous"><parent link="base"/><child link="wheel_link"/><origin xyz="0 2 0" rpy="1.5708 0 0"/><axis xyz="0 0 1"/></joint>
</robot>`;

export const ARM_SRDF = `<?xml version="1.0"?>
<robot name="arm">
  <group name="reach"><joint name="yaw"/><joint name="pitch"/><joint name="lift"/></group>
  <group name="grip"><joint name="finger"/></group>
  <end_effector name="gripper" parent_link="tool" group="grip" parent_group="reach"/>
  <group_state name="home" group="reach"><joint name="pitch" value="-0.5"/></group_state>
  <group_state name="raised" group="reach"><joint name="yaw" value="1.0"/><joint name="pitch" value="-1.0"/><joint name="lift" value="0.2"/></group_state>
  <group_state name="open" group="grip"><joint name="finger" value="0.04"/></group_state>
</robot>`;

// An SDF joint sits at its own pose and its child link at a static offset from it, so the
// joint frame and the child frame differ: the case the motion group exists for.
export const SWING_SDF = `<?xml version="1.0"?>
<sdf version="1.9"><model name="swing">
  <link name="base"><visual name="v"><pose>0 0 0.05 0 0 0</pose><geometry><box><size>0.4 0.4 0.1</size></box></geometry></visual></link>
  <link name="arm"><pose relative_to="hinge">0.05 0.1 0 0 0 0.4</pose><visual name="v"><pose>0.25 0 0 0 0 0</pose><geometry><box><size>0.5 0.08 0.06</size></box></geometry></visual></link>
  <link name="tip"><pose relative_to="slide">0 0 0.02 0 0 0</pose><visual name="v"><geometry><sphere><radius>0.04</radius></sphere></geometry></visual></link>
  <joint name="hinge" type="revolute"><pose relative_to="base">0 0 0.2 0 0.2 0</pose><parent>base</parent><child>arm</child><axis><xyz>0 1 0</xyz><limit><lower>-1.2</lower><upper>1.2</upper></limit></axis></joint>
  <joint name="slide" type="prismatic"><pose relative_to="arm">0.5 0 0 0 0 0</pose><parent>arm</parent><child>tip</child><axis><xyz>1 0 0</xyz><limit><lower>0</lower><upper>0.3</upper></limit></axis></joint>
</model></sdf>`;

export const parseArmUrdf = (xml = ARM_URDF) => withDom(() => parseUrdf(xml, { sourceUrl: "/robots/arm.urdf" }));
export const parseSwingSdf = (xml = SWING_SDF) => withDom(() => parseSdf(xml, { sourceUrl: "/robots/swing.sdf" }));
/** An SRDF's description: its URDF's, with the SRDF's semantics on it (as `loadRenderSrdf` builds it). */
export function parseArmSrdf() {
  const urdfData = parseArmUrdf();
  const srdf = withDom(() => parseSrdf(ARM_SRDF, { sourceUrl: "/robots/arm.srdf", urdfData }));
  return { ...urdfData, srdf };
}
/** A description with its once-built part list, and the mesh data the old solver poses as the oracle. */
export function robotOf(description, meshesByUrl = new Map()) {
  return { description, ...buildRobotParts(description, meshesByUrl), oracleMeshData: buildUrdfMeshGeometry(description, meshesByUrl, { lightweight: true }) };
}
