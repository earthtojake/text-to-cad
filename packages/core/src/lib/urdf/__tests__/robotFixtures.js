// Robot descriptions for the robot scene's tests, parsed by this package's own parsers.
// The parsers read a DOM (`DOMParser`), which Node does not have and this package does not
// depend on, so a small XML reader stands in for it: elements, attributes and text, which is
// all a URDF, an SRDF or an SDF uses. Primitives only: no mesh is fetched.
import {
  mergeBounds, multiplyTransforms, solveUrdfLinkWorldTransforms, transformBounds, buildUrdfVisualParts
} from "../kinematics.js";
import { parseSdf } from "../parseSdf.js";
import { parseSrdf } from "../parseSrdf.js";
import { parseUrdf } from "../parseUrdf.js";
import { buildRobotParts } from "../robotParts.js";

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'" };
const decode = text => text.replace(/&(amp|lt|gt|quot|apos);/g, (_, name) => ENTITIES[name]);

function element(tagName, attributes, parentNode) {
  const node = {
    nodeType: 1, tagName, localName: tagName.split(":").pop(), namespaceURI: null, parentNode, childNodes: [],
    getAttribute: name => (Object.hasOwn(attributes, name) ? attributes[name] : null),
    get textContent() { return node.childNodes.map(child => child.textContent).join(""); }
  };
  return node;
}

/** A document the robot parsers can read: `documentElement`, and no parse error. */
export function parseXml(text) {
  const root = { childNodes: [] };
  const stack = [root];
  const token = /<\?[\s\S]*?\?>|<!--[\s\S]*?-->|<\/([^\s>]+)\s*>|<([^\s/>]+)((?:\s+[^\s=/>]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>|([^<]+)/g;
  for (const match of text.matchAll(token)) {
    const [, closing, opening, attributeText, selfClosing, textRun] = match;
    const parent = stack[stack.length - 1];
    if (closing) {
      if (stack.length < 2 || parent.tagName !== closing) throw new Error(`unbalanced </${closing}>`);
      stack.pop();
    } else if (opening) {
      const attributes = {};
      for (const [, name, double, single] of (attributeText || "").matchAll(/([^\s=]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) {
        attributes[name] = decode(double ?? single);
      }
      const node = element(opening, attributes, parent.tagName ? parent : null);
      parent.childNodes.push(node);
      if (!selfClosing) stack.push(node);
    } else if (textRun !== undefined) {
      parent.childNodes.push({ nodeType: 3, textContent: decode(textRun), parentNode: parent });
    }
  }
  if (stack.length !== 1) throw new Error(`unclosed <${stack[stack.length - 1].tagName}>`);
  return { documentElement: root.childNodes.find(node => node.nodeType === 1) || null, querySelector: () => null };
}

function withXml(read) {
  const previous = globalThis.DOMParser;
  globalThis.DOMParser = class { parseFromString(text) { return parseXml(text); } };
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

export const parseArmUrdf = (xml = ARM_URDF) => withXml(() => parseUrdf(xml, { sourceUrl: "/robots/arm.urdf" }));
export const parseSwingSdf = (xml = SWING_SDF) => withXml(() => parseSdf(xml, { sourceUrl: "/robots/swing.sdf" }));
/** An SRDF's description: its URDF's, with the SRDF's semantics on it (as `loadRenderSrdf` builds it). */
export function parseArmSrdf() {
  const urdfData = parseArmUrdf();
  const srdf = withXml(() => parseSrdf(ARM_SRDF, { sourceUrl: "/robots/arm.srdf", urdfData }));
  return { ...urdfData, srdf };
}

/** A description with its once-built part list, as the robot renderer and the snapshot CLI load it. */
export function robotOf(description, meshesByUrl = new Map()) {
  return { description, ...buildRobotParts(description, meshesByUrl), oracleParts: buildUrdfVisualParts(description, meshesByUrl) };
}

/**
 * The ORACLE a robot scene is held to: the description solver's box around every visual at
 * `pose`, each visual's source box carried through its link's solved transform and its own.
 */
export function solvedBounds(robot, pose = {}) {
  const links = solveUrdfLinkWorldTransforms(robot.description, pose);
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  return mergeBounds(robot.oracleParts.map(part => transformBounds(part.sourceBounds,
    multiplyTransforms(links.get(part.linkName) || identity, part.localTransform))));
}
