import path from "node:path";

export function toPosixPath(value) {
  return String(value || "").split(path.sep).join("/");
}

export function encodePathParam(value) {
  return toPosixPath(value)
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

function relativePathStaysInsideRoot(relativePath) {
  return relativePath === "" || (
    relativePath !== ".." &&
    !relativePath.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relativePath)
  );
}

export function pathIsInside(childPath, parentPath) {
  const relativePath = path.relative(path.resolve(parentPath), path.resolve(childPath));
  return Boolean(relativePath) && relativePathStaysInsideRoot(relativePath);
}

export function pathIsInsideOrEqual(childPath, parentPath) {
  const relativePath = path.relative(path.resolve(parentPath), path.resolve(childPath));
  return relativePathStaysInsideRoot(relativePath);
}
