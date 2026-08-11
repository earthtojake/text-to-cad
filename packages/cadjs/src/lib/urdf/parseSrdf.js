function isPlainObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function localName(node) {
  return String(node?.localName || node?.tagName || "").split(":").pop();
}

function childElementsByTag(parent, tagName) {
  return Array.from(parent?.childNodes || []).filter((node) => node?.nodeType === 1 && localName(node) === tagName);
}

function parseSrdfStringArray(values, context) {
  const seen = new Set();
  return values.map((entry) => String(entry || "").trim()).filter((entry) => {
    if (!entry) {
      throw new Error(`${context} cannot include empty values`);
    }
    if (seen.has(entry)) {
      throw new Error(`${context} includes duplicate ${entry}`);
    }
    seen.add(entry);
    return true;
  });
}

function appendUnique(target, values) {
  const seen = new Set(target);
  for (const value of values) {
    if (!seen.has(value)) {
      target.push(value);
      seen.add(value);
    }
  }
}

function allJointNamesForChain(urdfData, baseLink, tipLink) {
  if (!baseLink || !tipLink || baseLink === tipLink) {
    return [];
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointsByParent = new Map();
  for (const joint of joints) {
    const parentLink = String(joint?.parentLink || "").trim();
    const childLink = String(joint?.childLink || "").trim();
    if (!parentLink || !childLink) {
      continue;
    }
    const current = jointsByParent.get(parentLink) || [];
    current.push(joint);
    jointsByParent.set(parentLink, current);
  }
  const stack = [[baseLink, []]];
  const visited = new Set();
  while (stack.length) {
    const [linkName, path] = stack.pop();
    if (linkName === tipLink) {
      return path;
    }
    if (visited.has(linkName)) {
      continue;
    }
    visited.add(linkName);
    for (const joint of [...(jointsByParent.get(linkName) || [])].reverse()) {
      const childLink = String(joint?.childLink || "").trim();
      const jointName = String(joint?.name || "").trim();
      if (childLink && jointName) {
        stack.push([childLink, [...path, jointName]]);
      }
    }
  }
  return [];
}

function jointNamesForGroup(group, urdfData, groupsByName, visiting = new Set()) {
  const jointByName = new Map((Array.isArray(urdfData?.joints) ? urdfData.joints : [])
    .map((joint) => [String(joint?.name || ""), joint])
    .filter(([name]) => name));
  const names = [];
  const explicitJointNames = Array.isArray(group?.jointNames) ? group.jointNames : [];
  if (explicitJointNames.length) {
    return explicitJointNames.filter((jointName) => {
      const joint = jointByName.get(String(jointName || ""));
      return joint && String(joint.type || "") !== "fixed" && !joint.mimic;
    });
  }
  for (const chain of Array.isArray(group?.chains) ? group.chains : []) {
    appendUnique(
      names,
      allJointNamesForChain(urdfData, String(chain?.baseLink || ""), String(chain?.tipLink || ""))
        .filter((jointName) => {
          const joint = jointByName.get(jointName);
          return joint && String(joint.type || "") !== "fixed" && !joint.mimic;
        })
    );
  }
  const groupName = String(group?.name || "");
  if (groupName) {
    visiting.add(groupName);
  }
  for (const subgroupName of Array.isArray(group?.subgroups) ? group.subgroups : []) {
    const key = String(subgroupName || "").trim();
    if (!key || visiting.has(key)) {
      continue;
    }
    const subgroup = groupsByName.get(key);
    if (subgroup) {
      appendUnique(names, jointNamesForGroup(subgroup, urdfData, groupsByName, visiting));
    }
  }
  return names;
}

function linkNamesForGroup(group, urdfData, groupsByName, visiting = new Set()) {
  const jointByName = new Map((Array.isArray(urdfData?.joints) ? urdfData.joints : [])
    .map((joint) => [String(joint?.name || ""), joint])
    .filter(([name]) => name));
  const links = new Set(Array.isArray(group?.linkNames) ? group.linkNames.map((link) => String(link || "")).filter(Boolean) : []);
  const addJointLinks = (jointName) => {
    const joint = jointByName.get(String(jointName || ""));
    const childLink = String(joint?.childLink || "").trim();
    if (childLink) {
      links.add(childLink);
    }
  };
  for (const jointName of Array.isArray(group?.jointNames) ? group.jointNames : []) {
    addJointLinks(jointName);
  }
  for (const chain of Array.isArray(group?.chains) ? group.chains : []) {
    const baseLink = String(chain?.baseLink || "").trim();
    const tipLink = String(chain?.tipLink || "").trim();
    if (tipLink) {
      links.add(tipLink);
    }
    for (const jointName of allJointNamesForChain(urdfData, baseLink, tipLink)) {
      addJointLinks(jointName);
    }
  }
  const groupName = String(group?.name || "");
  if (groupName) {
    visiting.add(groupName);
  }
  for (const subgroupName of Array.isArray(group?.subgroups) ? group.subgroups : []) {
    const key = String(subgroupName || "").trim();
    if (!key || visiting.has(key)) {
      continue;
    }
    const subgroup = groupsByName.get(key);
    if (subgroup) {
      for (const linkName of linkNamesForGroup(subgroup, urdfData, groupsByName, visiting)) {
        links.add(linkName);
      }
    }
  }
  return links;
}

function linkAdjacentToAnyLink(urdfData, parentLink, childLinks) {
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  return joints.some((joint) => {
    const jointParent = String(joint?.parentLink || "").trim();
    const jointChild = String(joint?.childLink || "").trim();
    return (jointParent === parentLink && childLinks.has(jointChild)) || (jointChild === parentLink && childLinks.has(jointParent));
  });
}

function disabledCollisionSource(reason) {
  const normalized = String(reason || "").trim().toLowerCase();
  if (normalized.includes("adjacent")) {
    return "adjacent";
  }
  if (["never", "always", "sample", "default"].some((token) => normalized.includes(token))) {
    return "sampled";
  }
  if (normalized.includes("setup") || normalized.includes("assistant")) {
    return "setup_assistant";
  }
  if (normalized.includes("assum")) {
    return "assumed";
  }
  return "manual";
}

function parsePlanningGroups(robot, urdfData) {
  const linkNames = new Set((Array.isArray(urdfData?.links) ? urdfData.links : []).map((link) => String(link?.name || "")).filter(Boolean));
  const jointNames = new Set((Array.isArray(urdfData?.joints) ? urdfData.joints : []).map((joint) => String(joint?.name || "")).filter(Boolean));
  const groupNames = new Set();
  const groups = childElementsByTag(robot, "group").map((groupElement) => {
    const name = String(groupElement.getAttribute("name") || "").trim();
    if (!name) {
      throw new Error("SRDF planning group name is required");
    }
    if (groupNames.has(name)) {
      throw new Error(`Duplicate SRDF planning group: ${name}`);
    }
    groupNames.add(name);

    const parsedJointNames = parseSrdfStringArray(
      childElementsByTag(groupElement, "joint").map((joint) => joint.getAttribute("name")),
      `SRDF planning group ${name} jointNames`
    );
    const parsedLinkNames = parseSrdfStringArray(
      childElementsByTag(groupElement, "link").map((link) => link.getAttribute("name")),
      `SRDF planning group ${name} linkNames`
    );
    for (const jointName of parsedJointNames) {
      if (!jointNames.has(jointName)) {
        throw new Error(`SRDF planning group ${name} references missing joint ${jointName}`);
      }
    }
    for (const linkName of parsedLinkNames) {
      if (!linkNames.has(linkName)) {
        throw new Error(`SRDF planning group ${name} references missing link ${linkName}`);
      }
    }
    const chains = childElementsByTag(groupElement, "chain").map((chain) => {
      const baseLink = String(chain.getAttribute("base_link") || "").trim();
      const tipLink = String(chain.getAttribute("tip_link") || "").trim();
      if (!linkNames.has(baseLink) || !linkNames.has(tipLink)) {
        throw new Error(`SRDF planning group ${name} chain references missing link`);
      }
      return { baseLink, tipLink };
    });
    const subgroups = parseSrdfStringArray(
      childElementsByTag(groupElement, "group").map((group) => group.getAttribute("name")),
      `SRDF planning group ${name} subgroups`
    );
    return {
      name,
      jointNames: parsedJointNames,
      linkNames: parsedLinkNames,
      chains,
      subgroups
    };
  });
  if (!groups.length) {
    throw new Error("SRDF must define at least one planning group");
  }
  for (const group of groups) {
    for (const subgroup of group.subgroups) {
      if (!groupNames.has(subgroup)) {
        throw new Error(`SRDF planning group ${group.name} references missing subgroup ${subgroup}`);
      }
    }
  }
  return groups;
}

function groupTipLink(group) {
  if (Array.isArray(group?.linkNames) && group.linkNames.length) {
    return String(group.linkNames[group.linkNames.length - 1] || "");
  }
  if (Array.isArray(group?.chains) && group.chains.length) {
    return String(group.chains[group.chains.length - 1]?.tipLink || "");
  }
  return "";
}

function endEffectorLink(endEffector, groupsByName) {
  return groupTipLink(groupsByName.get(endEffector.group)) || endEffector.parentLink;
}

function parseEndEffectors(robot, urdfData, planningGroups) {
  const linkNames = new Set((Array.isArray(urdfData?.links) ? urdfData.links : []).map((link) => String(link?.name || "")).filter(Boolean));
  const groupsByName = new Map(planningGroups.map((group) => [group.name, group]));
  const endEffectorNames = new Set();
  return childElementsByTag(robot, "end_effector").map((element) => {
    const name = String(element.getAttribute("name") || "").trim();
    if (!name) {
      throw new Error("SRDF end effector name is required");
    }
    if (endEffectorNames.has(name)) {
      throw new Error(`Duplicate SRDF end effector: ${name}`);
    }
    endEffectorNames.add(name);
    const parentLink = String(element.getAttribute("parent_link") || "").trim();
    const group = String(element.getAttribute("group") || "").trim();
    const parentGroup = String(element.getAttribute("parent_group") || "").trim();
    if (!linkNames.has(parentLink)) {
      throw new Error(`SRDF end effector ${name} references missing parent_link ${parentLink || "(missing)"}`);
    }
    if (!groupsByName.has(group)) {
      throw new Error(`SRDF end effector ${name} references missing group ${group || "(missing)"}`);
    }
    if (parentGroup && !groupsByName.has(parentGroup)) {
      throw new Error(`SRDF end effector ${name} references missing parent_group ${parentGroup}`);
    }
    const endEffector = { name, parentLink, group, parentGroup };
    const link = endEffectorLink(endEffector, groupsByName);
    if (!linkNames.has(link)) {
      throw new Error(`SRDF end effector ${name} references missing link ${link || "(missing)"}`);
    }
    const endEffectorLinks = linkNamesForGroup(groupsByName.get(group), urdfData, groupsByName);
    if (parentGroup) {
      const parentGroupLinks = linkNamesForGroup(groupsByName.get(parentGroup), urdfData, groupsByName);
      const overlap = [...endEffectorLinks].filter((linkName) => parentGroupLinks.has(linkName)).sort();
      if (overlap.length) {
        throw new Error(`SRDF end effector ${name} group shares link(s) with parent_group: ${overlap.join(", ")}`);
      }
      if (!parentGroupLinks.has(parentLink)) {
        throw new Error(`SRDF end effector ${name} parent_link is not in parent_group ${parentGroup}`);
      }
    }
    if (endEffectorLinks.size && !endEffectorLinks.has(parentLink) && !linkAdjacentToAnyLink(urdfData, parentLink, endEffectorLinks)) {
      throw new Error(`SRDF end effector ${name} parent_link is not adjacent to its group`);
    }
    return {
      ...endEffector,
      link
    };
  });
}

function parseGroupStates(robot, urdfData, planningGroups) {
  const groupNames = new Set(planningGroups.map((group) => group.name));
  const groupsByName = new Map(planningGroups.map((group) => [group.name, group]));
  const jointByName = new Map((Array.isArray(urdfData?.joints) ? urdfData.joints : []).map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  const stateNamesByGroup = new Set();
  return childElementsByTag(robot, "group_state").map((element) => {
    const name = String(element.getAttribute("name") || "").trim();
    const group = String(element.getAttribute("group") || "").trim();
    if (!name || !groupNames.has(group)) {
      throw new Error(`SRDF group_state ${name || "(missing)"} references missing group ${group || "(missing)"}`);
    }
    const stateKey = `${group}/${name}`;
    if (stateNamesByGroup.has(stateKey)) {
      throw new Error(`Duplicate SRDF group_state ${stateKey}`);
    }
    stateNamesByGroup.add(stateKey);
    const groupJointNames = new Set(jointNamesForGroup(groupsByName.get(group), urdfData, groupsByName));
    const seenJointNames = new Set();
    const jointValuesByName = {};
    for (const jointElement of childElementsByTag(element, "joint")) {
      const jointName = String(jointElement.getAttribute("name") || "").trim();
      const value = Number(jointElement.getAttribute("value"));
      const joint = jointByName.get(jointName);
      if (!joint || !Number.isFinite(value)) {
        throw new Error(`SRDF group_state ${name} has invalid joint value ${jointName || "(missing)"}`);
      }
      if (seenJointNames.has(jointName)) {
        throw new Error(`SRDF group_state ${name} includes duplicate joint ${jointName}`);
      }
      seenJointNames.add(jointName);
      if (!groupJointNames.has(jointName)) {
        throw new Error(`SRDF group_state ${name} joint ${jointName} is not in group ${group}`);
      }
      if (String(joint.type || "") === "fixed" || joint.mimic) {
        throw new Error(`SRDF group_state ${name} cannot set fixed or mimic joint ${jointName}`);
      }
      if (String(joint.type || "") !== "continuous") {
        const lower = String(joint.type || "") === "revolute" ? Number(joint.minValueDeg) * (Math.PI / 180) : Number(joint.minValueDeg);
        const upper = String(joint.type || "") === "revolute" ? Number(joint.maxValueDeg) * (Math.PI / 180) : Number(joint.maxValueDeg);
        if (Number.isFinite(lower) && value < lower) {
          throw new Error(`SRDF group_state ${name} joint ${jointName} is below its URDF lower limit`);
        }
        if (Number.isFinite(upper) && value > upper) {
          throw new Error(`SRDF group_state ${name} joint ${jointName} is above its URDF upper limit`);
        }
      }
      jointValuesByName[jointName] = value;
    }
    return { name, group, jointValuesByName, jointValuesByNameRad: jointValuesByName };
  });
}

function parseDisabledCollisionPairs(robot, urdfData) {
  const linkNames = new Set((Array.isArray(urdfData?.links) ? urdfData.links : []).map((link) => String(link?.name || "")).filter(Boolean));
  const seenPairs = new Set();
  return childElementsByTag(robot, "disable_collisions").map((element) => {
    const link1 = String(element.getAttribute("link1") || "").trim();
    const link2 = String(element.getAttribute("link2") || "").trim();
    const reason = String(element.getAttribute("reason") || "").trim();
    if (!linkNames.has(link1) || !linkNames.has(link2)) {
      throw new Error("SRDF disabled collision pair references missing link");
    }
    if (link1 === link2) {
      throw new Error("SRDF disabled collision pair cannot repeat the same link");
    }
    const pairKey = [link1, link2].sort().join("/");
    if (seenPairs.has(pairKey)) {
      throw new Error(`Duplicate SRDF disabled collision pair ${pairKey}`);
    }
    seenPairs.add(pairKey);
    if (!reason) {
      throw new Error(`SRDF disabled collision pair ${pairKey} requires a reason`);
    }
    return {
      link1,
      link2,
      reason,
      source: disabledCollisionSource(reason)
    };
  });
}

export function motionFromSrdf(srdf) {
  if (!isPlainObject(srdf)) {
    return null;
  }
  return {
    transport: "moveit2Server",
    planningGroups: srdf.planningGroups,
    endEffectors: srdf.endEffectors,
    groupStates: srdf.groupStates,
    disabledCollisionPairs: srdf.disabledCollisionPairs,
    srdf
  };
}

export function parseSrdf(xmlText, { sourceUrl = "", urdfData = null } = {}) {
  if (typeof DOMParser === "undefined") {
    throw new Error("DOMParser is unavailable in this environment");
  }
  const document = new DOMParser().parseFromString(String(xmlText || ""), "application/xml");
  const parseError = document.querySelector("parsererror");
  if (parseError) {
    throw new Error("Failed to parse SRDF XML");
  }
  const robot = document.documentElement;
  if (!robot || robot.tagName !== "robot") {
    throw new Error("SRDF root element must be <robot>");
  }
  const robotName = String(robot.getAttribute("name") || "").trim();
  if (!robotName) {
    throw new Error("SRDF robot name is required");
  }
  if (urdfData?.robotName && urdfData.robotName !== robotName) {
    // Pairing is by colocated URDF with a matching robot name; the caller
    // resolves the URDF (catalog relations), this guards against mispairing.
    throw new Error("SRDF robot name must match the paired URDF robot name");
  }
  const planningGroups = parsePlanningGroups(robot, urdfData);
  const endEffectors = parseEndEffectors(robot, urdfData, planningGroups);
  const groupStates = parseGroupStates(robot, urdfData, planningGroups);
  const disabledCollisionPairs = parseDisabledCollisionPairs(robot, urdfData);
  return {
    kind: "texttocad-srdf",
    srdf: sourceUrl,
    robotName,
    planningGroups,
    endEffectors,
    groupStates,
    disabledCollisionPairs
  };
}
