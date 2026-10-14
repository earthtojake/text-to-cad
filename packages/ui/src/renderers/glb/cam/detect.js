/**
 * Whether a loaded glTF scene is a CAM result (`cadgen cam plan`): cadgen cam wrote it (`generator` in the
 * extras of the scene or a node) and it carries the job's extras (`cam`). Its own small module, free of the CAM
 * viewer, so GlbRenderer can ask before that viewer's chunk is fetched.
 */

export const CAM_GENERATOR = "cadgen cam";

const plainObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** The `cam` extras an object of the scene carries, or null. */
export const camExtras = (object) => (plainObject(object?.userData?.cam) ? object.userData.cam : null);

export function carriesCamJob(root) {
  let generator = false;
  let extras = false;
  root?.traverse?.((object) => {
    if (object?.userData?.generator === CAM_GENERATOR) generator = true;
    if (camExtras(object)) extras = true;
  });
  return generator && extras;
}
