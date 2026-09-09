import {
  sidebarDirectoryIdForEntry,
  sidebarDirectoryPath
} from "./sidebar.js";

export function collapsedBreadcrumbNodes(nodes) {
  if (!Array.isArray(nodes) || nodes.length <= 4) {
    return (Array.isArray(nodes) ? nodes : []).map((node) => ({ type: "node", node }));
  }

  return [
    { type: "node", node: nodes[0] },
    { type: "ellipsis", label: "...", nodes: nodes.slice(1, -2) },
    ...nodes.slice(-2).map((node) => ({ type: "node", node }))
  ];
}

export function ellipsisBreadcrumbMenuDirectory(node) {
  if (node?.type === "directory") {
    return node?.directory || node?.menuDirectory || null;
  }
  return node?.menuDirectory || null;
}

export function directoryTitle(directory) {
  return String(directory?.id || directory?.name || "Directory");
}

function parentDirectoryForPath(directoryPath, index) {
  if (!Array.isArray(directoryPath) || index < 0 || index >= directoryPath.length) {
    return null;
  }
  return index > 0 ? directoryPath[index - 1] : directoryPath[index] || null;
}

export function buildBreadcrumbNodes({
  directoryTree,
  selectedEntry,
  selectedFileLabel,
  selectedFileTitle
}) {
  if (!directoryTree) {
    if (selectedEntry) {
      return [{
        type: "entry",
        label: selectedFileLabel,
        title: selectedFileTitle,
        entry: selectedEntry,
        menuDirectory: null
      }];
    }
    return [{
      type: "placeholder",
      label: selectedFileLabel,
      title: selectedFileTitle,
      menuDirectory: null
    }];
  }

  if (!selectedEntry) {
    return [{
      type: "placeholder",
      label: selectedFileLabel,
      title: selectedFileTitle,
      menuDirectory: directoryTree
    }];
  }

  const directoryId = sidebarDirectoryIdForEntry(selectedEntry);
  const directoryPath = sidebarDirectoryPath(directoryTree, directoryId);
  const directoryNodes = directoryPath
    .map((directory, index) => {
      const id = String(directory?.id || "").trim();
      if (!id) {
        return null;
      }
      return {
        type: "directory",
        id,
        label: String(directory?.name || "Folder"),
        title: directoryTitle(directory),
        directory,
        menuDirectory: parentDirectoryForPath(directoryPath, index)
      };
    })
    .filter(Boolean);

  const containingDirectory = directoryPath[directoryPath.length - 1] || directoryTree;

  return [
    ...directoryNodes,
    {
      type: "entry",
      label: selectedFileLabel,
      title: selectedFileTitle,
      entry: selectedEntry,
      menuDirectory: containingDirectory
    }
  ];
}
